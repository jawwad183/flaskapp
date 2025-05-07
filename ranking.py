import pandas as pd
import numpy as np
import re
import openai
from transformers import pipeline
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from spellchecker import SpellChecker
from sentence_transformers import SentenceTransformer, util
import os
from dotenv import load_dotenv

# Setup
stop_words = set(stopwords.words("english"))
slang_words = {"u", "ur", "lol", "omg", "btw", "brb", "thx", "pls", "plz"}
spell = SpellChecker()

# Deferred-loaded global models
_sentiment_pipeline = None
_embedding_model = None
_aspect_embeddings = None

# Static data
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

aspects = [
    "price", "quality", "design", "durability", "usability", "value", "performance", "service", "delivery", "packaging",
    "fit", "material", "protection", "grip", "texture", "buttons", "camera cutout", "style", "color", "port access",
    "charging speed", "connectivity", "compatibility", "cable length", "plug fit", "power delivery", "heating", "port quality", "charging reliability",
    "adhesion", "clarity", "touch sensitivity", "bubble", "scratch resistance", "installation", "fingerprint resistance", "thickness", "coverage", "transparency"
]

def init_models():
    """Loads all ML models into global memory if not already loaded."""
    global _sentiment_pipeline, _embedding_model, _aspect_embeddings

    if _sentiment_pipeline is None or _embedding_model is None or _aspect_embeddings is None:
        print("🔁 Loading models...")
        _sentiment_pipeline = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        _aspect_embeddings = _embedding_model.encode(aspects, convert_to_tensor=True)
        print("✅ Models loaded.")

def clean_review(text):
    if pd.isna(text):
        return ""
    text = text.lower()
    contractions = {
        "n't": " not", "'re": " are", "'s": " is", "'d": " would",
        "'ll": " will", "'t": " not", "'ve": " have", "'m": " am"
    }
    for k, v in contractions.items():
        text = text.replace(k, v)
    text = re.sub(r'[^a-z\s]', '', text)
    tokens = word_tokenize(text)
    filtered = [
        word for word in tokens
        if word not in stop_words and word not in slang_words and len(word) > 2 and word in spell
    ]
    return ' '.join(filtered)

def extract_aspects(text, threshold=0.25):
    init_models()
    review_embedding = _embedding_model.encode(text, convert_to_tensor=True)
    cos_scores = util.pytorch_cos_sim(review_embedding, _aspect_embeddings)[0]
    return [(aspects[i], float(score)) for i, score in enumerate(cos_scores) if score >= threshold]

def compute_review_rank(aspect_list, review_sentiment_score, user_prefs, user_sentiment_bias):
    matched_aspects = [aspect for aspect, _ in aspect_list]
    match_count = sum(1 for aspect in matched_aspects if aspect in user_prefs)
    match_ratio = match_count / max(len(user_prefs), 1)
    sentiment_alignment = 1.0 - abs(user_sentiment_bias - review_sentiment_score)
    sentiment_alignment = max(0.0, sentiment_alignment)
    return round(0.5 * match_ratio + 0.5 * sentiment_alignment, 4)

def generate_summary(top_reviews, user_preferences, user_sentiment_bias):
    init_models()

    top_reviews_text = "\n\n".join("- " + r for r in top_reviews["review_body"])
    extracted_aspects = set()
    for aspect_list in top_reviews["aspects"]:
        extracted_aspects.update([a[0] for a in aspect_list])

    if user_sentiment_bias >= 0.7:
        tone = "positive and confident"
    elif user_sentiment_bias >= 0.4:
        tone = "slightly optimistic but realistic"
    else:
        tone = "neutral with some cautious observations"

    prompt = f"""
    The user values the following product qualities most: {', '.join(user_preferences)}.

    Summarize the following customer reviews in 3-4 fluent, natural sentences. Focus specifically on the strengths and weaknesses related to what the user cares about. Avoid generic phrases like "good quality" unless supported by actual review content. Use a {tone} tone that matches the user's sentiment bias.

    Customer Reviews:
    {top_reviews_text}

    Key aspects frequently mentioned in these reviews: {', '.join(sorted(extracted_aspects))}

    Write ONLY the summary as one coherent paragraph. No bullet points. No extra explanations.
    """.strip()

    from openai import OpenAI
    client = OpenAI(api_key=openai.api_key)

    response = client.chat.completions.create(
        model="gpt-4-0125-preview",
        messages=[
            {"role": "system", "content": "You are a product review analyst."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=300
    )

    return response.choices[0].message.content.strip()

def get_sentiment_label(bias):
    if bias >= 0.65:
        return "Positive"
    elif bias >= 0.35:
        return "Neutral"
    else:
        return "Negative"

def run_review_pipeline(email, product_id, category):
    init_models()

    preferences_df = pd.read_excel("data/preferences.xlsx")
    review_df = pd.read_excel("data/review.xlsx")
    product_reviews_df = pd.read_csv("data/selected_products_for_user_study.csv")

    user_pref_row = preferences_df[preferences_df["Email"] == email]
    if user_pref_row.empty:
        return [], "User preferences not found."

    general_prefs = user_pref_row["General Preferences"].values[0].split(",")
    if category.lower().startswith("phone"):
        category_prefs = user_pref_row["Phone Case & Cover Preferences"].values[0].split(",")
    elif "charger" in category.lower():
        category_prefs = user_pref_row["Chargers and Cables Preferences"].values[0].split(",")
    elif "screen" in category.lower():
        category_prefs = user_pref_row["Screen Protectors Preferences"].values[0].split(",")
    else:
        category_prefs = []

    prefs = [p.strip().lower() for p in general_prefs + category_prefs if p.strip()]

    user_reviews = review_df[review_df["Email"] == email]
    if user_reviews.empty:
        return [], "User onboarding reviews not found."

    sentiment_scores = []
    for text in user_reviews["Review"].dropna().values[:3]:
        result = _sentiment_pipeline(text)[0]
        score = result["score"] if result["label"] == "POSITIVE" else 1 - result["score"]
        sentiment_scores.append(score)
    user_sentiment_bias = np.mean(sentiment_scores) if sentiment_scores else 0.5

    product_reviews = product_reviews_df[product_reviews_df["product_id"] == product_id].copy()
    if product_reviews.empty:
        return [], "No reviews found for this product."

    product_reviews["cleaned_review"] = product_reviews["review_body"].apply(clean_review)
    product_reviews["sentiment_score"] = product_reviews["cleaned_review"].apply(
        lambda text: _sentiment_pipeline(text)[0]["score"]
        if _sentiment_pipeline(text)[0]["label"] == "POSITIVE"
        else 1 - _sentiment_pipeline(text)[0]["score"]
    )
    product_reviews["aspects"] = product_reviews["cleaned_review"].apply(extract_aspects)

    product_reviews["ranking_score"] = product_reviews.apply(
        lambda row: compute_review_rank(row["aspects"], row["sentiment_score"], prefs, user_sentiment_bias),
        axis=1
    )

    ranked_reviews = product_reviews.sort_values(by="ranking_score", ascending=False).head(10)
    summary = generate_summary(ranked_reviews.head(3), prefs, user_sentiment_bias)
    sentiment_label = get_sentiment_label(user_sentiment_bias)

    results = ranked_reviews[["review_body", "star_rating", "sentiment_score", "ranking_score", "aspects"]].to_dict(orient="records")
    return results, summary, sentiment_label
