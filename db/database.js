const fs = require("fs");
const path = require("path");
const Database = require("better-sqlite3");

const DB_PATH = path.join(__dirname, "tecnocambia.sqlite");
const SCHEMA_PATH = path.join(__dirname, "schema.sql");

function openDb() {
  const db = new Database(DB_PATH);
  db.pragma("journal_mode = WAL");
  db.pragma("foreign_keys = ON");
  return db;
}

function ensureSchema(db) {
  const schema = fs.readFileSync(SCHEMA_PATH, "utf8");
  db.exec(schema);
}

function initDb() {
  const db = openDb();
  ensureSchema(db);
  return db;
}

module.exports = {
  DB_PATH,
  initDb,
};

