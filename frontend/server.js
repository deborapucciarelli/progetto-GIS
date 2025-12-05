// server.js
const express = require('express');
const app = express();
const port = 8000;

// Servi cartella corrente
app.use(express.static(__dirname));

app.listen(port, () => {
  console.log(`Server avviato: http://localhost:${port}`);
});
