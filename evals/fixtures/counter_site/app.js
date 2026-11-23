const countEl = document.getElementById('count');
const incrementBtn = document.getElementById('increment');

let count = Number(localStorage.getItem('count') || 0);

function render() {
  countEl.textContent = count;
}

function save() {
  localStorage.setItem('count', String(count));
}

incrementBtn.addEventListener('click', () => {
  count += 1;
  save();
  render();
});

render();
