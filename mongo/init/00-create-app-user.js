// Runs once on an empty volume, connected as the root user.
// Creates the readWrite user that the backend connects with.
const dbName = process.env.MONGO_INITDB_DATABASE || "dispora";
const user = process.env.MONGO_APP_USER;
const pwd = process.env.MONGO_APP_PASSWORD;

if (!user || !pwd) {
  throw new Error("MONGO_APP_USER and MONGO_APP_PASSWORD must be set");
}

db.getSiblingDB(dbName).createUser({
  user,
  pwd,
  roles: [{ role: "readWrite", db: dbName }],
});
print(`created user ${user} on ${dbName}`);
