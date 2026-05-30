FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci --frozen-lockfile

COPY . .

# Build for production
RUN npm run build

# Copy built files to a location that can be shared
RUN mkdir -p /static && cp -r dist/* /static/

EXPOSE 3000

# For development
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]