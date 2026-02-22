# Content Creation App

An AI-powered web application that acts as your personal content creation assistant. It automates the heavy lifting of video production, from conducting deep research to writing scripts, and even generating images and audio!

## 🌟 What It Does

- **Deep Research**: Tell it a topic, and it uses Google Gemini to surf the web and compile a comprehensive research dossier.
- **Scriptwriting**: Automatically generates structured video scripts based on the research.
- **Media Generation**: Connects to AI models to generate text-to-speech (TTS) voiceovers and matching background images for your video scenes.
- **Project Management**: Saves your progress to your account in the cloud so you can pick up where you left off.

## 🛠️ Technology used
- **Frontend**: Clean, modern web UI built with HTML, CSS, and JavaScript.
- **Backend / Server**: Python Flask server processing all the AI workloads.
- **AI Engine**: Google Gemini API (for text, images, and research).
- **Database & Auth**: Google Firebase (Firestore for database, Authentication for user logins).
- **Hosting**: Designed to run locally or be deployed instantly to Google Cloud Run.

## 💻 How to Run It Locally

### 1. Install Requirements
Make sure you have Python installed, then install the required packages:
```bash
pip install -r requirements.txt
```

### 2. Add Your Keys
Create a `.env` file in the main folder and add your Google Gemini API Key:
```
GEMINI_API_KEY=your_gemini_api_key_here
```

### 3. Start the Server
Run the provided startup script in your terminal:
```bash
sh run_server.sh
```
*(Alternatively, you can run `export PYTHONPATH=$PYTHONPATH:$(pwd)/execution && python3 execution/server.py`)*

### 4. Open the App
Open your web browser and go to: **http://localhost:8080**

## 🚀 How to Deploy to Google Cloud

If you want to put this app on the live internet, you can use the built-in deployment script.
Make sure you have the Google Cloud CLI (`gcloud`) installed.

Run the deployment script:
```bash
sh deploy.sh
```
This will automatically package the app using the `Dockerfile` and push it to Google Cloud Run!
