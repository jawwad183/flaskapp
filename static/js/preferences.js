document.getElementById('preferencesForm').addEventListener('submit', function(event) {
    const categories = ['Printers', 'Printer Cartridges', 'Shredders'];
    let valid = true;
  
    categories.forEach(category => {
      const selected = document.querySelectorAll(`input[name='${category}']:checked`).length;
      if (selected < 5) {
        alert(`Please select at least 5 preferences for ${category}`);
        valid = false;
      }
    });
  
    if (!valid) {
      event.preventDefault();
    }
  });