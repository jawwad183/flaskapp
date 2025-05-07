from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import pandas as pd
import os
import re
import json
import random
from threading import Thread
from spellchecker import SpellChecker
from ranking import run_review_pipeline

app = Flask(__name__)
app.secret_key = 'your_super_secret_key_123'

# File paths
EXCEL_FILE = 'data/users.xlsx'
PREFERENCES_FILE = 'data/preferences.xlsx'
PRODUCTS_FILE = 'data/unique_products.csv'
REVIEW_FILE = 'data/review.xlsx'
SELECTED_REVIEW_FILE = 'data/selected_products_for_user_study.csv'
CACHE_DIR = 'cache'
os.makedirs(CACHE_DIR, exist_ok=True)

spell = SpellChecker()

def clean_text(text):
    if not isinstance(text, str):
        return ""
    words = re.findall(r'\b\w+\b[.,!?;:]*', text)
    cleaned = []
    for word in words:
        core = re.sub(r'[^\w]', '', word).lower()
        if spell.known([core]):
            if len(core) == 1 and core not in {'i', 'a'}:
                continue
            cleaned.append(word)
    return ' '.join(cleaned)

def cache_file(email):
    return os.path.join(CACHE_DIR, f"{email}_pipeline.json")

def load_cached_pipeline(email):
    path = cache_file(email)
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}

def precompute_pipeline(email, reviewed_products):
    result_map = {}
    for product in reviewed_products:
        pid = product["product_id"]
        cat = product["sub_category"]
        ranked, summary, label = run_review_pipeline(email, pid, cat)
        result_map[pid] = {
            "ranked": ranked,
            "summary": summary,
            "sentiment_label": label
        }
    with open(cache_file(email), "w") as f:
        json.dump(result_map, f)

def get_user_data():
    email = session.get('email')
    if not email:
        return None, None, [], {}

    preferences = pd.read_excel(PREFERENCES_FILE)
    preferences = preferences[preferences['Email'] == email].to_dict(orient='records')[0]

    review_df = pd.read_excel(REVIEW_FILE)
    user_reviews = review_df[review_df['Email'] == email]
    reviewed_ids = user_reviews['Product ID'].unique().tolist()

    product_df = pd.read_csv(PRODUCTS_FILE)
    product_df['Image_path'] = '/static/images/' + product_df['Image_path']

    selected_reviews = pd.read_csv(SELECTED_REVIEW_FILE)
    selected_reviews['cleaned_review'] = selected_reviews['review_body'].apply(clean_text)

    avg_ratings = selected_reviews.groupby('product_id')['star_rating'].mean().round(1).reset_index()
    avg_ratings.columns = ['product_id', 'avg_rating']
    product_df = product_df.merge(avg_ratings, on='product_id', how='left')

    reviewed_products = product_df[product_df['product_id'].isin(reviewed_ids)].head(3).reset_index(drop=True)

    unranked_reviews = (
    selected_reviews[['product_id', 'cleaned_review', 'star_rating']]
    .dropna()
    .groupby('product_id')
    .apply(lambda x: x.drop(columns='product_id').to_dict(orient='records'))
    .to_dict()
    )


    pipeline_data = load_cached_pipeline(email)
    return preferences, reviewed_products.to_dict(orient='records'), unranked_reviews, pipeline_data

def initialize_evaluation_flow(email, products):
    randomized_products = products.copy()
    random.shuffle(randomized_products)
    screen_order_map = {i: random.sample(['unranked', 'ranked', 'summary'], 3) for i in range(len(products))}
    session['evaluation_flow'] = {
        'products': randomized_products,
        'screen_orders': screen_order_map
    }

@app.route("/signup_loading")
def signup_loading():
    return render_template("signup_loading.html")

@app.route("/")
def signup_page():
    return render_template("signup.html")   # This is the full signup form

@app.route("/warmup_models")
def warmup_models():
    from ranking import init_models  # Import here to delay loading
    email = session.get("email")
    if not email:
        return jsonify({"ready": False})

    # Step 1: load ML models
    init_models()

    # Step 2: Run review pipeline and cache it
    _, reviewed_products, _, _ = get_user_data()
    precompute_pipeline(email, reviewed_products)
    initialize_evaluation_flow(email, reviewed_products)

    return jsonify({"ready": True})

@app.route("/signup_ready")
def signup_ready():
    return jsonify({"ready": True})  # You can enhance this with real checks if needed

@app.route("/submit", methods=["POST"])
def submit_form():
    if not request.is_json:
        return jsonify({'success': False, 'message': 'Invalid request format.'}), 400
    data = request.get_json()
    email, name, age_group = data.get('email', '').strip(), data.get('name', '').strip(), data.get('age', '').strip()
    preferences_map = {
        'General Preferences': data.get('ordered_general', '').strip(),
        'Phone Case & Cover Preferences': data.get('ordered_phone', '').strip(),
        'Chargers and Cables Preferences': data.get('ordered_charger', '').strip(),
        'Screen Protectors Preferences': data.get('ordered_screen', '').strip()
    }

    if '@' not in email or not (email.endswith('.com') or email.endswith('kfupm.edu.sa')):
        return jsonify({'success': False, 'message': 'Invalid email format.'}), 400
    if not name.replace(" ", "").isalpha():
        return jsonify({'success': False, 'message': 'Name must contain only alphabets.'}), 400
    if not age_group:
        return jsonify({'success': False, 'message': 'Please select an age group.'}), 400
    if any(len([v for v in value.split(',') if v.strip()]) < 5 for value in preferences_map.values()):
        return jsonify({'success': False, 'message': 'At least 5 preferences required per category.'}), 400

    df = pd.read_excel(EXCEL_FILE)
    if email in df['Email'].values:
        return jsonify({'success': False, 'message': 'This email is already registered.'}), 400
    df = pd.concat([df, pd.DataFrame([{'Email': email, 'Name': name, 'Age Group': age_group}])], ignore_index=True)
    df.to_excel(EXCEL_FILE, index=False)

    pref_df = pd.read_excel(PREFERENCES_FILE)
    pref_df = pref_df[pref_df['Email'] != email]
    pref_df = pd.concat([pref_df, pd.DataFrame([{'Email': email, **preferences_map}])], ignore_index=True)
    pref_df.to_excel(PREFERENCES_FILE, index=False)

    session['email'] = email
    return jsonify({'success': True, 'redirect': url_for('signup_loading')}), 200

@app.route("/review")
def review_screen():
    df = pd.read_csv(PRODUCTS_FILE)
    df['video'] = '/static/videos/' + df['video']
    products = df.to_dict(orient='records')
    categories = sorted(df['sub_category'].dropna().unique())
    return render_template('reviews.html', products=products, categories=categories)

@app.route("/save_review", methods=["POST"])
def save_review():
    email = session.get('email')
    if not email:
        return "Session expired", 400

    # Save the reviews (unchanged)
    reviews = request.get_json()
    df_products = pd.read_csv(PRODUCTS_FILE)
    product_map = df_products.set_index('product_id').to_dict('index')
    review_data = []
    for entry in reviews:
        pid = entry['product_id']
        if pid in product_map:
            product = product_map[pid]
            review_data.append({
                'Email': email,
                'Product ID': pid,
                'Product Title': product['title'],
                'Category': product['sub_category'],
                'Rating': entry['rating'],
                'Review': entry['review']
            })

    review_df = pd.DataFrame(review_data)
    if os.path.exists(REVIEW_FILE):
        existing = pd.read_excel(REVIEW_FILE)
        review_df = pd.concat([existing, review_df], ignore_index=True)
    review_df.to_excel(REVIEW_FILE, index=False)

    # ✅ Trigger pipeline and initialize randomized flow
    _, reviewed_products, _, _ = get_user_data()
    Thread(target=precompute_pipeline, args=(email, reviewed_products)).start()
    initialize_evaluation_flow(email, reviewed_products)

    # ✅ Redirect to first step using router logic
    return redirect(url_for("loading_screen"))

@app.route("/loading")
def loading_screen():
    return render_template("loading.html")

@app.route("/check_pipeline_ready")
def check_pipeline_ready():
    email = session.get('email')
    if not email:
        return jsonify({"ready": False})
    
    pipeline_data = load_cached_pipeline(email)
    _, reviewed_products, _, _ = get_user_data()

    expected_product_ids = {str(p['product_id']) for p in reviewed_products}
    cached_product_ids = set(pipeline_data.keys())

    all_ready = expected_product_ids.issubset(cached_product_ids)
    return jsonify({"ready": all_ready})

@app.route("/evaluation/<int:index>/<int:step>", methods=["GET", "POST"])
def evaluation_router(index, step):
    flow = session.get('evaluation_flow')
    if not flow:
        return redirect(url_for("evaluation_complete"))

    if index >= len(flow['products']):
        return redirect(url_for("evaluation_complete"))

    # ✅ FIX: Ensure we convert index to string if screen_orders keys are strings
    screen_sequence = flow['screen_orders'].get(str(index)) or flow['screen_orders'].get(index)
    if not screen_sequence:
        return redirect(url_for("evaluation_complete"))

    if step >= len(screen_sequence):
        return redirect(url_for("evaluation_router", index=index + 1, step=0))

    screen = screen_sequence[step]
    return redirect(url_for(f"evaluation_{screen}", index=index, step=step))

@app.route("/evaluation/unranked/<int:index>/<int:step>", methods=["GET", "POST"])
def evaluation_unranked(index, step):
    preferences, products, unranked_map, cached_data = get_user_data()
    product = session['evaluation_flow']['products'][index]
    product_id = product['product_id']
    reset = request.args.get("reset") == "true"

    if request.method == "POST":
        return redirect(url_for("evaluation_router", index=index, step=step + 1))

    return render_template("evaluation/unranked.html",
        product=product,
        reviews=unranked_map.get(product_id, []),
        current_index=index,
        total_products=len(products),
        step=step,
        next_url=url_for("evaluation_router", index=index, step=step + 1),
        products_json=products,
        unranked_reviews_json=unranked_map,
        reset_form=reset
    )

@app.route("/evaluation/ranked/<int:index>/<int:step>", methods=["GET", "POST"])
def evaluation_ranked(index, step):
    preferences, products, unranked_map, cached_data = get_user_data()
    product = session['evaluation_flow']['products'][index]
    product_id = product['product_id']
    reset = request.args.get("reset") == "true"
    reviews = cached_data.get(product_id, {}).get("ranked", [])

    if request.method == "POST":
        return redirect(url_for("evaluation_router", index=index, step=step + 1))

    return render_template("evaluation/ranked.html",
        product=product,
        reviews=reviews,
        current_index=index,
        total_products=len(products),
        step=step,
        next_url=url_for("evaluation_router", index=index, step=step + 1),
        products_json=products,
        unranked_reviews_json=unranked_map,
        reset_form=reset
    )

@app.route("/evaluation/summary/<int:index>/<int:step>", methods=["GET", "POST"])
def evaluation_summary(index, step):
    preferences, products, unranked_map, cached_data = get_user_data()
    product = session['evaluation_flow']['products'][index]
    product_id = product['product_id']
    reset = request.args.get("reset") == "true"
    summary = cached_data.get(product_id, {}).get("summary", "Summary is still being generated...")

    if request.method == "POST":
        return redirect(url_for("evaluation_router", index=index, step=step + 1))

    return render_template("evaluation/summary.html",
        product=product,
        summary_text=summary,
        current_index=index,
        total_products=len(products),
        step=step,
        next_url=url_for("evaluation_router", index=index, step=step + 1),
        products_json=products,
        unranked_reviews_json=unranked_map,
        reset_form=reset
    )

@app.route("/evaluation/complete")
def evaluation_complete():
    return render_template("thankyou.html")

@app.route("/submit_eval", methods=["POST"])
def submit_eval():
    data = request.get_json()

    print("📥 Received payload:", json.dumps(data, indent=2))
    print("🔢 Step number:", data.get("step"))
    print("🆔 Product ID:", data.get("product_id"))
    print("📦 Sub-category (from front-end):", data.get("sub_category"))

    email = session.get("email")
    if not email:
        return "Unauthorized", 403

    # Extract values from submitted JSON
    step_number = data.get("step", -1)
    product_id = data.get("product_id")
    time_spent = data.get("time_spent")
    justification = data.get("justification", "").strip()

    # Raw option texts from front-end
    satisfaction_text = data.get("satisfaction", "")
    confidence_text = data.get("confidence", "")
    preference_text = data.get("preference_match", "")
    ease_text = data.get("ease_of_finding", "")
    decision_text = data.get("purchase_decision", "").strip().lower()

    # Mappings from text to numeric values
    satisfaction_map = {
        "Very dissatisfied": 1,
        "Dissatisfied": 2,
        "Neutral": 3,
        "Satisfied": 4,
        "Very satisfied": 5
    }
    confidence_map = {
        "Not confident at all": 1,
        "Slightly confident": 2,
        "Moderately confident": 3,
        "Quite confident": 4,
        "Very confident": 5
    }
    preference_map = {
        "Not well at all": 1,
        "Slightly well": 2,
        "Moderately well": 3,
        "Quite well": 4,
        "Very well": 5
    }
    ease_map = {
        "Very difficult": 1,
        "Difficult": 2,
        "Neutral": 3,
        "Easy": 4,
        "Very easy": 5
    }
    decision_map = {
        "yes": 1,
        "no": 2
    }

    # Convert using maps (default to 0 if not matched)
    q1 = satisfaction_map.get(satisfaction_text, 0)
    q2 = confidence_map.get(confidence_text, 0)
    q3 = preference_map.get(preference_text, 0)
    q4 = ease_map.get(ease_text, 0)
    q5 = decision_map.get(decision_text, 0)

    # Get sub_category using product_id
    sub_category = ""
    try:
        product_df = pd.read_csv(PRODUCTS_FILE)
        product_row = product_df[product_df["product_id"].astype(str) == str(product_id)]
        if not product_row.empty:
            sub_category = product_row.iloc[0]["sub_category"]
    except Exception as e:
        print(f"⚠️ Error reading product info: {e}")

    result = {
        "email": email,
        "product_id": product_id,
        "screen": step_number,
        "q1": q1,
        "q2": q2,
        "q3": q3,
        "q4": q4,
        "q5": q5,
        "justify": justification,
        "time": time_spent,
        "sub_category": sub_category
    }

    # Save to results.xlsx
    result_file = "data/results.xlsx"
    columns = ["email", "product_id", "screen", "q1", "q2", "q3", "q4", "q5", "justify", "time", "sub_category"]

    try:
        # Check for duplicate submission
        if os.path.exists(result_file):
            df = pd.read_excel(result_file)
        else:
            df = pd.DataFrame(columns=columns)

        already_submitted = df[
            (df["email"] == email) &
            (df["product_id"] == product_id) &
            (df["screen"] == step_number)
        ]

        if not already_submitted.empty:
            print("⚠️ Duplicate evaluation detected. Submission blocked.")
            return jsonify({"success": False, "error": "Evaluation for this screen has already been submitted."}), 400

        df = pd.concat([df, pd.DataFrame([result])], ignore_index=True)

        print("📄 Writing to Excel with columns:", df.columns.tolist())
        print("🆕 New row to write:", result)

        df.to_excel(result_file, index=False)
        print("✅ Form data saved to results.xlsx")
        return jsonify({"success": True})

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Failed to save result: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
