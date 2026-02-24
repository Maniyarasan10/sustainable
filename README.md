# Sustainable Community App - Frontend

A React Native mobile application built with Expo and TypeScript for community issue reporting and voting.

## Features

- 📱 User registration and login with mobile number
- 🗳️ Upvote/downvote community issues
- 📍 Live geolocation tagging for issues
- 🏠 Real-time issue feed sorted by votes
- ➕ Create new issues with location and description
- 🎨 Modern, clean UI with smooth animations

## Tech Stack

- **React Native** with **Expo**
- **TypeScript** for type safety
- **React Navigation** for routing
- **Expo Location** for geolocation
- **Axios** for API calls
- **AsyncStorage** for local data persistence

## Prerequisites

- Node.js (v16 or higher)
- npm or yarn
- Expo CLI (`npm install -g expo-cli`)
- iOS Simulator (for Mac) or Android Studio (for Android development)

## Installation

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Update the API base URL in `src/services/api.ts`:
   ```typescript
   const API_BASE_URL = 'http://YOUR_BACKEND_URL:8000/api';
   ```
   
   For local development:
   - iOS Simulator: `http://localhost:8000/api`
   - Android Emulator: `http://10.0.2.2:8000/api`
   - Physical device: `http://YOUR_LOCAL_IP:8000/api`

## Running the App

1. Start the Expo development server:
   ```bash
   npm start
   ```

2. Choose your platform:
   - Press `i` for iOS Simulator
   - Press `a` for Android Emulator
   - Scan QR code with Expo Go app on physical device

## Project Structure

```
frontend/
├── src/
│   ├── components/          # Reusable components
│   │   └── IssueCard.tsx
│   ├── navigation/          # Navigation configuration
│   │   └── AppNavigator.tsx
│   ├── screens/            # App screens
│   │   ├── LoginScreen.tsx
│   │   ├── RegisterScreen.tsx
│   │   ├── HomeScreen.tsx
│   │   └── CreateIssueScreen.tsx
│   ├── services/           # API services
│   │   └── api.ts
│   └── types/              # TypeScript types
│       └── index.ts
├── App.tsx                 # Main app entry point
├── app.json               # Expo configuration
└── package.json           # Dependencies
```

## Environment Setup

For iOS development, add location permissions to `app.json`:
```json
"ios": {
  "infoPlist": {
    "NSLocationWhenInUseUsageDescription": "This app needs location access"
  }
}
```

For Android, permissions are already configured in `app.json`.

## Building for Production

### iOS
```bash
expo build:ios
```

### Android
```bash
expo build:android
```

## Features Guide

### User Registration
- Enter name, mobile number, date of birth, gender, and address
- Mobile number is used as the unique identifier

### Home Screen
- View all community issues sorted by vote count
- Upvote/downvote issues
- Pull to refresh
- Tap + button to create new issue

### Creating Issues
- Enter issue title and description
- Automatic location detection
- Submit to share with community

## Troubleshooting

**Location not working:**
- Ensure location permissions are granted in device settings
- For iOS simulator, use "Features > Location > Custom Location"
- For Android emulator, use Extended Controls > Location

**API connection issues:**
- Verify backend is running
- Check API_BASE_URL in api.ts
- Ensure device/emulator is on same network (for physical devices)

## License

MIT License