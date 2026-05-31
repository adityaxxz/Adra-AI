let tasks = [];

function saveTasks() {
    localStorage.setItem('tasks', JSON.stringify(tasks));
}

function loadTasks() {
    const storedTasks = localStorage.getItem('tasks');
    if (storedTasks) {
        tasks = JSON.parse(storedTasks);
    } else {
        tasks = [];
    }
}

function renderTasks() {
    const taskList = document.getElementById('task-list');
    taskList.innerHTML = ''; // Clear existing tasks

    tasks.forEach(task => {
        const listItem = document.createElement('li');
        listItem.classList.add('todo-item');
        listItem.setAttribute('data-id', task.id);
        if (task.completed) {
            listItem.classList.add('completed');
        }

        listItem.innerHTML = `
            <span class="task-text">${task.text}</span>
            <button class="complete-button" data-action="complete">✔</button>
            <button class="delete-button" data-action="delete">✖</button>
        `;
        taskList.appendChild(listItem);
    });
}

function addTask(taskText) {
    if (taskText.trim() === "") return;
    const newTask = {
        id: Date.now(), // Unique ID
        text: taskText.trim(),
        completed: false
    };
    tasks.push(newTask);
    saveTasks();
    renderTasks();
}

function toggleComplete(taskId) {
    tasks = tasks.map(task =>
        task.id == taskId ? { ...task, completed: !task.completed } : task
    );
    saveTasks();
    renderTasks();
}

function deleteTask(taskId) {
    tasks = tasks.filter(task => task.id != taskId);
    saveTasks();
    renderTasks();
}

// Event listener for form submission
const todoForm = document.getElementById('todo-form');
const newTaskInput = document.getElementById('new-task-input');

todoForm.addEventListener('submit', (event) => {
    event.preventDefault(); // Prevent default form submission

    const taskText = newTaskInput.value;
    if (taskText.trim() !== '') {
        addTask(taskText);
        newTaskInput.value = ''; // Clear the input field
    }
});

// Event delegation for task actions (complete/delete)
const taskList = document.getElementById('task-list');

taskList.addEventListener('click', (event) => {
    const target = event.target;

    // Check if the clicked element is a button with data-action
    if (target.tagName === 'BUTTON' && target.hasAttribute('data-action')) {
        const action = target.dataset.action;
        const listItem = target.closest('.todo-item'); // Find the parent li
        
        if (!listItem) return; // Should not happen if structure is correct

        const taskId = parseInt(listItem.dataset.id); // Get task ID from parent li

        if (action === 'complete') {
            toggleComplete(taskId);
        } else if (action === 'delete') {
            deleteTask(taskId);
        }
    }
});

// Initialize the application on page load
function init() {
    loadTasks();
    renderTasks();
}

document.addEventListener('DOMContentLoaded', init);