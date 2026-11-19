FROM mongo:8.0

# Files in init/ run in name order, ONLY when the data volume is empty.
# 00-create-app-user.js creates the least-privilege API user.
# 10-import.sh imports the seed JSON files below, applies the kategori fix and creates indexes.
COPY init/ /docker-entrypoint-initdb.d/
# Seed data (copy of mongodb-dispora-export.zip) that 10-import.sh reads.
COPY seed/ /opt/dispora/seed/
# Make the .sh executable so the entrypoint runs it as a child process instead of sourcing it.
RUN chmod +x /docker-entrypoint-initdb.d/*.sh
