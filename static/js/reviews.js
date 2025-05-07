// Parse product data from embedded JSON in HTML
const allProducts = JSON.parse(document.getElementById("product-data").textContent);

// Group products by category
function groupByCategory(products) {
  const grouped = {};
  products.forEach(product => {
    const category = product.sub_category;
    if (!grouped[category]) grouped[category] = [];
    grouped[category].push({
      id: product.product_id,
      title: product.title,
      image: product.image,
      video: product.video,
      category: category
    });
  });
  return grouped;
}

const categories = groupByCategory(allProducts);

let selectedRatings = {};
let selectedReviews = {};
let submittedReviews = {};
let reviewedCategories = new Set();

// DOM Elements
const productVideo = document.getElementById("productVideo");
const productImage = document.getElementById("productImage");
const productTitle = document.getElementById("productTitle");
const reviewBox = document.getElementById("review");
const submitBtn = document.getElementById("submitBtn");
const nextBtn = document.getElementById("nextBtn");
const stars = document.querySelectorAll(".star");

// Highlight star ratings
function highlightStars(rating) {
  stars.forEach(star => {
    star.classList.toggle("selected", parseInt(star.dataset.value) <= rating);
  });
}

// Get product category by ID
function getProductCategoryById(id) {
  for (let category in categories) {
    if (categories[category].some(p => p.id.toString() === id)) {
      return category;
    }
  }
  return "";
}

// Attach product card click listeners
function attachCardListeners() {
  const reviewedList = JSON.parse(localStorage.getItem("reviewedProducts") || "[]");

  document.querySelectorAll(".product-card").forEach(card => {
    const id = card.getAttribute("data-id");

    if (reviewedList.includes(id)) {
      // Visually indicate it's reviewed
      card.style.opacity = 0.5;
      card.style.pointerEvents = "none";
      card.title = "✅ Already reviewed";
      return;
    }

    card.addEventListener("click", () => {
      const title = card.getAttribute("data-title");
      const image = card.getAttribute("data-image");
      const video = card.getAttribute("data-video");
      const category = getProductCategoryById(id);

      productVideo.src = video || "";
      productImage.src = image;
      productTitle.textContent = title;

      reviewBox.value = selectedReviews[id] || "";
      highlightStars(selectedRatings[id] || 0);

      reviewBox.setAttribute("data-id", id);
      reviewBox.setAttribute("data-category", category);
    });
  });
}

// Star rating interactions
stars.forEach(star => {
  star.addEventListener("mouseover", () => {
    highlightStars(star.dataset.value);
  });

  star.addEventListener("mouseout", () => {
    const currentId = reviewBox.getAttribute("data-id");
    highlightStars(selectedRatings[currentId] || 0);
  });

  star.addEventListener("click", () => {
    const currentId = reviewBox.getAttribute("data-id");
    if (!currentId) return;
    selectedRatings[currentId] = parseInt(star.dataset.value);
    highlightStars(selectedRatings[currentId]);
  });
});

// Review box live validation (draft tracking)
reviewBox.addEventListener("input", () => {
  const currentId = reviewBox.getAttribute("data-id");
  const category = reviewBox.getAttribute("data-category");
  if (!currentId || !category) return;

  reviewBox.value = reviewBox.value.replace(/[^a-zA-Z .,!?'"()\n\r]/g, "");

  const wordCount = reviewBox.value.trim().split(/\s+/).filter(w => w.length > 0).length;

  if (wordCount >= 30 && wordCount <= 100) {
    selectedReviews[currentId] = reviewBox.value;
    if (selectedRatings[currentId]) {
      reviewedCategories.add(category);
    }
  } else {
    delete selectedReviews[currentId];
  }
});

// Submit review handler
submitBtn.addEventListener("click", () => {
  const productId = reviewBox.getAttribute("data-id");
  const category = reviewBox.getAttribute("data-category");
  const rating = selectedRatings[productId];
  const review = reviewBox.value.trim();

  const wordCount = review.split(/\s+/).filter(w => w.length > 0).length;

  if (!productId || !category || !rating || !review || wordCount < 30 || wordCount > 100) {
    alert("❌ Please complete both rating and a 30–100 word review before submitting.");
    return;
  }

  const isDuplicateText = Object.values(submittedReviews).some(prev => prev === review);
  if (isDuplicateText) {
    alert("⚠️ This exact review text has already been submitted for another product.");
    return;
  }

  const product = categories[category].find(p => p.id === productId);

  const payload = [{
    product_id: productId,
    title: product.title,
    category: product.category,
    rating: rating,
    review: review
  }];

  fetch("/save_review", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  })
    .then(res => res.text())
    .then(msg => {
      alert("✅ Review saved for current product.");

      // Save review in memory
      submittedReviews[productId] = review;
      selectedReviews[productId] = review;
      reviewedCategories.add(category);

      // Store reviewed product in localStorage
      const reviewedList = JSON.parse(localStorage.getItem("reviewedProducts") || "[]");
      if (!reviewedList.includes(productId)) {
        reviewedList.push(productId);
        localStorage.setItem("reviewedProducts", JSON.stringify(reviewedList));
      }

      // Clear UI
      highlightStars(0);
      reviewBox.value = "";
    })
    .catch(err => {
      console.error(err);
      alert("❌ Error saving review.");
    });
});

// Next button: validate and move to loading screen
nextBtn.addEventListener("click", () => {
  console.log("➡️ Next button clicked");

  const reviewed = Object.keys(categories).every(category => {
    return categories[category].some(product => {
      return selectedRatings[product.id] && selectedReviews[product.id];
    });
  });

  if (!reviewed) {
    alert("❌ Please rate and review at least one product from each category before proceeding.");
    return;
  }

  // ✅ Save reviewed product IDs to localStorage
  const reviewedIds = Object.keys(submittedReviews);
  localStorage.setItem("reviewedProducts", JSON.stringify(reviewedIds));

  console.log("✅ All categories reviewed. Redirecting...");
  setTimeout(() => {
    window.location.assign("/loading");
  }, 100);
});

// Init on load
document.addEventListener("DOMContentLoaded", () => {
  attachCardListeners();
  const firstCard = document.querySelector(".product-card:not([style*='pointer-events: none'])");
  if (firstCard) firstCard.click();
});
