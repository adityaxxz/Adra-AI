let gameBoard = ["", "", "", "", "", "", "", "", ""];
let currentPlayer = 'X';
let gameActive = true;

const winningConditions = [
    [0, 1, 2],
    [3, 4, 5],
    [6, 7, 8],
    [0, 3, 6],
    [1, 4, 7],
    [2, 5, 8],
    [0, 4, 8],
    [2, 4, 6]
];

const gameStatusDisplay = document.getElementById('game-status');
const cells = document.querySelectorAll('.cell');
const resetButton = document.getElementById('reset-button');

function updateStatus(message) {
    gameStatusDisplay.innerHTML = message;
}

function handleCellClick(event) {
    const clickedCell = event.target;
    const clickedCellIndex = parseInt(clickedCell.getAttribute('data-cell-index'));

    if (gameBoard[clickedCellIndex] !== "" || !gameActive) {
        return;
    }

    gameBoard[clickedCellIndex] = currentPlayer;
    clickedCell.innerHTML = currentPlayer;
    clickedCell.classList.add('player-' + currentPlayer.toLowerCase());

    if (checkWin()) {
        return;
    }

    if (checkDraw()) {
        return;
    }

    currentPlayer = currentPlayer === 'X' ? 'O' : 'X';
    updateStatus(currentPlayer + "'s turn");
}

function checkWin() {
    let roundWon = false;
    for (let i = 0; i < winningConditions.length; i++) {
        const winCondition = winningConditions[i];
        let a = gameBoard[winCondition[0]];
        let b = gameBoard[winCondition[1]];
        let c = gameBoard[winCondition[2]];

        if (a === '' || b === '' || c === '') {
            continue;
        }
        if (a === b && b === c) {
            roundWon = true;
            break;
        }
    }

    if (roundWon) {
        updateStatus(currentPlayer + " has won!");
        gameActive = false;
        return true;
    }
    return false;
}

function checkDraw() {
    let roundDraw = !gameBoard.includes("");
    if (roundDraw) {
        updateStatus("It's a draw!");
        gameActive = false;
        return true;
    }
    return false;
}

function resetGame() {
    gameBoard = ["", "", "", "", "", "", "", "", ""];
    currentPlayer = 'X';
    gameActive = true;
    cells.forEach(cell => {
        cell.innerHTML = '';
        cell.classList.remove('player-x', 'player-o');
    });
    updateStatus(currentPlayer + "'s turn");
}

// Event Listeners
cells.forEach(cell => cell.addEventListener('click', handleCellClick));
resetButton.addEventListener('click', resetGame);

// Initial game setup
resetGame();