document.addEventListener('DOMContentLoaded', () => {

  const preferences = {
    general: ['price', 'quality', 'design', 'durability', 'usability', 'value', 'performance', 'service', 'delivery', 'packaging'],
    phone: ['fit', 'material', 'protection', 'grip', 'texture', 'buttons', 'camera cutout', 'style', 'color', 'port access'],
    charger: ['charging speed', 'connectivity', 'compatibility', 'cable length', 'plug fit', 'power delivery', 'heating', 'port quality', 'durability', 'charging reliability'],
    screen: ['adhesion', 'clarity', 'touch sensitivity', 'bubble', 'scratch resistance', 'installation', 'fingerprint resistance', 'thickness', 'coverage', 'transparency']
  };

  const selectedPrefs = {
    general: [],
    phone: [],
    charger: [],
    screen: []
  };

  // Populate preference dropdowns
  function populateDropdowns() {
    Object.entries(preferences).forEach(([category, items]) => {
      const select = document.getElementById(`${category}Pref`);
      select.innerHTML = '<option value="">-- Select --</option>';
      items.forEach(item => {
        const option = document.createElement('option');
        option.value = item;
        option.textContent = item;
        select.appendChild(option);
      });
      select.addEventListener('change', () => handleSelect(select, category));
    });
  }

  // Handle selection
  function handleSelect(selectElem, category) {
    const value = selectElem.value;
    if (!value || selectedPrefs[category].includes(value)) return;
    selectedPrefs[category].push(value);
    updateList(category);
    updateDropdown(category);
    selectElem.value = '';
  }

  // Update tags
  function updateList(category) {
    const listContainer = document.getElementById(`${category}List`);
    const hiddenInput = document.getElementById(`ordered_${category}`);
    listContainer.innerHTML = '';

    selectedPrefs[category].forEach((item, index) => {
      const tag = document.createElement('div');
      tag.className = 'preference-tag';
      tag.innerHTML = `
        <span>${index + 1}. ${item}</span>
        <button type="button" onclick="removePref('${category}', '${item}')">&times;</button>
      `;
      listContainer.appendChild(tag);
    });

    hiddenInput.value = selectedPrefs[category].join(',');
  }

  // Remove preference
  window.removePref = function (category, item) {
    selectedPrefs[category] = selectedPrefs[category].filter(i => i !== item);
    updateList(category);
    updateDropdown(category);
  };

  // Refresh dropdown
  function updateDropdown(category) {
    const select = document.getElementById(`${category}Pref`);
    const allOptions = preferences[category];
    const selected = selectedPrefs[category];
    select.innerHTML = '<option value="">-- Select --</option>';
    allOptions.forEach(option => {
      if (!selected.includes(option)) {
        const opt = document.createElement('option');
        opt.value = option;
        opt.textContent = option;
        select.appendChild(opt);
      }
    });
  }

  // AJAX form submit
  document.getElementById('signupForm').addEventListener('submit', async function (event) {
    event.preventDefault();

    const form = event.target;
    const formData = new FormData(form);
    const jsonData = {};
    formData.forEach((value, key) => {
      jsonData[key] = value;
    });

    try {
      const response = await fetch('/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(jsonData)
      });

      const result = await response.json();

      if (!response.ok || !result.success) {
        alert(result.message || "An error occurred during submission.");
      } else {
        
        // ✅ Clear old reviews for a fresh session
        localStorage.removeItem("reviewedProducts");
        // ✅ Redirect to signup loading screen instead of review
        window.location.href = "/signup_loading";
      }
    } catch (error) {
      console.error(error);
      alert("Network error: failed to submit the form.");
    }
  });

  // Initialize on page load
  populateDropdowns();
});
