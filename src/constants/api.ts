import { Platform } from 'react-native';

// Si vous utilisez un vrai appareil, remplacez par votre IP locale (ex: 'http://192.168.1.100:8000')
const LOCAL_HOST = Platform.select({
  android: 'http://10.0.2.2:8000',
  ios: 'http://localhost:8000',
  default: 'http://localhost:8000',
});

export const API_BASE_URL = LOCAL_HOST;
