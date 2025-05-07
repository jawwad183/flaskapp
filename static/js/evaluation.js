console.log("🚀 evaluation.js loaded");

document.addEventListener("DOMContentLoaded", () => {
    const screenStartTime = Date.now();

    // ✅ Attempt to load embedded product and review data
    let products = [];
    let unrankedMap = {};

    try {
        const productDataEl = document.getElementById("product-data");
        const unrankedDataEl = document.getElementById("unranked-data");

        if (!productDataEl || !unrankedDataEl) {
            throw new Error("Missing JSON data elements");
        }

        products = JSON.parse(productDataEl.textContent);
        unrankedMap = JSON.parse(unrankedDataEl.textContent);
        console.log("✅ Loaded products and unranked reviews");
    } catch (e) {
        console.error("❌ Failed to parse JSON data:", e);
        return;
    }

    const form = document.getElementById("evaluation-form");
    const productImg = document.getElementById("product-img");
    const nextBtn = document.getElementById("next-btn");

    if (!form || !nextBtn || !productImg) {
        console.error("❌ Required DOM elements missing (form, next button, or product image)");
        return;
    }

    // ✅ Reset form if ?reset=true in URL
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get("reset") === "true") {
        console.log("🔄 Resetting form due to ?reset=true");
        form.reset();
    }

    nextBtn.addEventListener("click", async () => {
        console.log("🟢 'Next' button clicked");

        const screenEndTime = Date.now();
        const timeSpentSeconds = Math.round((screenEndTime - screenStartTime) / 1000);
        console.log(`⏱️ Time spent on screen: ${timeSpentSeconds} seconds`);

        // ✅ Validate required fields
        const requiredFields = [
            "satisfaction",
            "confidence",
            "preference_match",
            "ease_of_finding",
            "purchase_decision"
        ];

        let isValid = true;
        const missing = [];

        requiredFields.forEach(name => {
            const selected = form.querySelector(`input[name="${name}"]:checked`);
            if (!selected) {
                isValid = false;
                missing.push(name);
            }
        });

        if (!isValid) {
            console.warn("⚠️ Validation failed. Missing:", missing);
            alert("⚠️ Please select an option for all required questions.");
            const firstMissing = form.querySelector(`input[name="${missing[0]}"]`);
            if (firstMissing) {
                firstMissing.scrollIntoView({ behavior: "smooth", block: "center" });
                firstMissing.focus();
            }
            return;
        }

        // ✅ Prepare payload
        const productId = productImg.dataset.productId;
        const subCategory = productImg.dataset.subCategory || "";

        const product = products.find(p => String(p.product_id) === productId);
        const email = document.getElementById("user-info")?.dataset?.email || "";

        const screenPath = window.location.pathname;
        const screenType = screenPath.includes("/unranked") ? "unranked" :
                           screenPath.includes("/ranked") ? "ranked" :
                           screenPath.includes("/summary") ? "summary" : "unknown";

        const pathParts = screenPath.split("/");
        const stepRaw = pathParts[pathParts.length - 1];
        const stepNumber = parseInt(stepRaw);
        const validStep = isNaN(stepNumber) ? -1 : stepNumber;

        const formData = {
            satisfaction: form.querySelector(`input[name="satisfaction"]:checked`)?.value || "",
            confidence: form.querySelector(`input[name="confidence"]:checked`)?.value || "",
            preference_match: form.querySelector(`input[name="preference_match"]:checked`)?.value || "",
            ease_of_finding: form.querySelector(`input[name="ease_of_finding"]:checked`)?.value || "",
            purchase_decision: form.querySelector(`input[name="purchase_decision"]:checked`)?.value || "",
            justification: form.querySelector("textarea[name='justification']")?.value.trim() || ""
        };

        const payload = {
            email,
            screen: screenType,
            step: validStep,
            product_id: productId,
            sub_category: subCategory,
            time_spent: timeSpentSeconds,
            ...formData
        };

        console.log("📦 Sending evaluation data:", payload);

        try {
            const response = await fetch("/submit_eval", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            const result = await response.json();

            if (result.success) {
                console.log("✅ Submission successful");
                window.location.href = nextBtn.dataset.nextUrl;
            } else if (result.error?.includes("already been submitted")) {
                alert("⚠️ This product has already been evaluated. You will be moved to the next screen.");
                window.location.href = nextBtn.dataset.nextUrl;
            } else {
                console.error("❌ Server returned error:", result.error);
                alert("❌ Failed to save. Please try again.");
            }

        } catch (err) {
            console.error("❌ Submit request failed:", err);
            alert("⚠️ Network error or server is unreachable.");
        }
    });
});
