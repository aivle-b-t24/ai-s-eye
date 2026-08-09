FROM node:22-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
COPY docker-entrypoint.sh /usr/local/bin/dashboard-entrypoint

EXPOSE 5173

ENTRYPOINT ["sh", "/usr/local/bin/dashboard-entrypoint"]
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
