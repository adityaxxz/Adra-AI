// Calculator logic
// Select DOM elements
const display = document.getElementById('display');
const buttons = document.querySelectorAll('.btn');

// State variables
let currentOperand = '';
let previousOperand = '';
let operation = null;

/**
 * Append a digit (or decimal point) to the current operand.
 * @param {string} number
 */
function appendNumber(number) {
  // Prevent multiple leading zeros
  if (number === '0' && currentOperand === '0') return;
  // Simple concatenation – works for multi‑digit numbers
  currentOperand = `${currentOperand}${number}`;
}

/**
 * Choose an arithmetic operation.
 * Moves the current operand to the previous slot and stores the operation.
 * @param {string} op Symbol of the operation (+, -, *, /)
 */
function chooseOperation(op) {
  if (currentOperand === '') return; // nothing to operate on
  if (previousOperand !== '') {
    // If there is already a pending operation, compute it first
    compute();
  }
  operation = op;
  previousOperand = currentOperand;
  currentOperand = '';
}

/**
 * Perform the calculation based on the stored operation.
 */
function compute() {
  const prev = parseFloat(previousOperand);
  const curr = parseFloat(currentOperand);
  if (isNaN(prev) || isNaN(curr)) return;

  let result;
  switch (operation) {
    case '+':
      result = prev + curr;
      break;
    case '-':
      result = prev - curr;
      break;
    case '*':
      result = prev * curr;
      break;
    case '/':
      if (curr === 0) {
        // Division by zero – show error and reset state
        currentOperand = 'Error';
        previousOperand = '';
        operation = null;
        updateDisplay();
        return;
      }
      result = prev / curr;
      break;
    default:
      return;
  }

  // Store result as the new current operand
  currentOperand = result.toString();
  previousOperand = '';
  operation = null;
}

/**
 * Reset the calculator to its initial state.
 */
function clearAll() {
  currentOperand = '';
  previousOperand = '';
  operation = null;
}

/**
 * Update the calculator display.
 */
function updateDisplay() {
  display.textContent = currentOperand || '0';
}

// Attach event listeners to each button
buttons.forEach((button) => {
  button.addEventListener('click', () => {
    const action = button.dataset.action;
    const value = button.dataset.value; // used for digits

    if (action === 'digit' && value !== undefined) {
      appendNumber(value);
    } else if (action === 'add') {
      chooseOperation('+');
    } else if (action === 'subtract') {
      chooseOperation('-');
    } else if (action === 'multiply') {
      chooseOperation('*');
    } else if (action === 'divide') {
      chooseOperation('/');
    } else if (action === 'equals') {
      compute();
    } else if (action === 'clear') {
      clearAll();
    }
    // Refresh the display after handling the button press
    updateDisplay();
  });
});

// Initialise display on page load
updateDisplay();
