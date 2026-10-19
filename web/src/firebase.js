import { initializeApp } from 'firebase/app';
import { getAnalytics, isSupported } from 'firebase/analytics';

const firebaseConfig = {
  apiKey: 'AIzaSyD8VTbPXCpzoueWV_JS8x_IxpTmBhJHQ0Q',
  authDomain: 'reharmonized-custom.firebaseapp.com',
  projectId: 'reharmonized-custom',
  storageBucket: 'reharmonized-custom.firebasestorage.app',
  messagingSenderId: '1026546006041',
  appId: '1:1026546006041:web:347f242fd6c3de0289d288',
  measurementId: 'G-42R217CLCH',
};

const app = initializeApp(firebaseConfig);

isSupported()
  .then((supported) => {
    if (supported) getAnalytics(app);
  })
  .catch((error) => {
    console.warn('[Firebase] Analytics is unavailable:', error);
  });