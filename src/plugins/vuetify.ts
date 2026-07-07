import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import { createVuetify } from 'vuetify'

export default createVuetify({
  theme: {
    defaultTheme: 'ymDark',
    themes: {
      ymDark: {
        dark: true,
        colors: {
          background: '#070f1d',
          surface: '#0f2038',
          card: '#16324f',
          primary: '#00c2ff',
          secondary: '#00e0a0',
          warning: '#ffb020',
          error: '#ff5470',
          info: '#5fb3ff'
        }
      }
    }
  }
})
