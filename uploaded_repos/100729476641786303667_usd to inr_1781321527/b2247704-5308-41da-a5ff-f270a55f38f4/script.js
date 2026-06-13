const CONVERSION_RATE = 95;

const usdInput = document.getElementById('usd-amount');
const inrDisplay = document.getElementById('inr-amount');
const convertButton = document.getElementById('convert-button');

function convertUsdToInr() {
    const usdValue = parseFloat(usdInput.value);

    if (isNaN(usdValue)) {
        inrDisplay.value = 'Invalid input';
        return;
    }

    const inrValue = usdValue * CONVERSION_RATE;
    inrDisplay.value = inrValue.toFixed(2); // Display with 2 decimal places
}

// Add event listeners
if (convertButton) {
    convertButton.addEventListener('click', convertUsdToInr);
}

// If you want to trigger conversion on input change, uncomment the following:
// if (usdInput) {
//     usdInput.addEventListener('input', convertUsdToInr);
// }