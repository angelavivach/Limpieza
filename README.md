# Gmail Cleaner

Aplicación web para eliminar correos comerciales de Gmail de forma rápida y sencilla, directamente desde el navegador.

**App en producción:** [https://limpieza-pye0.onrender.com](https://limpieza-pye0.onrender.com)

---

## Funcionalidades

- Acceso protegido por contraseña
- Soporte de múltiples cuentas de Gmail
- Selección individual de correos antes de borrar
- Los correos marcados como favoritos nunca se eliminan
- Eliminación masiva de correos no leídos
- Los correos van a la papelera (30 días para recuperarlos)

## Filtros disponibles

| Filtro | Descripción |
|--------|-------------|
| Promociones | Categoría de promociones de Gmail |
| Newsletters | Correos con "unsubscribe" o "darse de baja" |
| AliExpress | Correos de AliExpress |
| PayPal | Correos de PayPal |
| Amazon | Correos de Amazon |
| Confirmaciones de compra | Pedidos, envíos, confirmaciones |
| DHL | Correos de DHL |
| GLS | Correos de GLS |
| Correos | Correos de Correos España |
| No-reply | Correos automáticos |
| Vinted | Correos de Vinted |
| Wallapop | Correos de Wallapop |
| Spotify | Correos de Spotify |
| Notificaciones Google | Alertas y recordatorios de Google |
| No leídos | Todos los correos sin leer |

---

## Despliegue

### Variables de entorno necesarias

| Variable | Descripción |
|----------|-------------|
| `APP_PASSWORD` | Contraseña para acceder a la app |
| `SECRET_KEY` | Clave secreta para las sesiones |
| `GOOGLE_CLIENT_ID` | Client ID de Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | Client Secret de Google Cloud Console |
| `REDIRECT_URI` | `https://TU-DOMINIO/auth/callback` |

### Google Cloud Console

1. Crear un proyecto en [console.cloud.google.com](https://console.cloud.google.com)
2. Activar la **Gmail API**
3. Configurar la pantalla de consentimiento OAuth (tipo Externo)
4. Crear credenciales -> **ID de cliente OAuth** -> tipo **Aplicación web**
5. Añadir la URI de redireccionamiento: `https://TU-DOMINIO/auth/callback`
6. Añadir los usuarios de prueba en **Google Auth Platform -> Audience**

### Estructura del proyecto

```
gmail-cleaner/
├── app.py              # Servidor Flask principal
├── requirements.txt    # Dependencias Python
├── Procfile            # Configuración para Railway/Render
├── render.yaml         # Configuración para Render
└── static/
    └── index.html      # Interfaz web
```

---

## Uso local

```bash
# Instalar dependencias
pip3 install --break-system-packages -r requirements.txt

# Ejecutar
python3 app.py
```

La app estará disponible en `http://localhost:8765`

---

## Notas

- Los correos se mueven a la papelera, no se eliminan permanentemente
- Tienes 30 días para recuperar correos desde la papelera de Gmail
- Los correos marcados con estrella están protegidos y nunca se eliminan
- En el tier gratuito de Render la app puede tardar unos 30 segundos en arrancar si lleva un rato sin usarse
