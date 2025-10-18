AlpinePulse JAR server
======================

This Spring Boot server serves the built web UI from a single executable JAR.

Build steps
----------

1) Build the frontend

   cd ../../web
   npm install
   npm run build

This creates `web/dist/`.

2) Copy the build into the server's static resources

   rm -rf ../java-server/src/main/resources/static/*
   cp -R dist/* ../java-server/src/main/resources/static/

3) Build the JAR

   cd ../java-server
   mvn spring-boot:run             # run directly (downloads deps on first run)
   # or
   mvn -DskipTests package         # creates target/alpinepulse-server-0.1.0.jar

4) Launch the JAR

   java -jar target/alpinepulse-server-0.1.0.jar

Open http://localhost:8080

Notes
-----
- The SPA fallback is configured, so deep links like `/planner` work.
- Replace `web/public/images/hero.jpg` to change the homepage background.
- If you change frontend code, rebuild and re-copy the new `dist` contents.
