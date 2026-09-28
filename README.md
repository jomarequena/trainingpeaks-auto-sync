# 🚀 TrainingPeaks Auto Sync (GitHub Actions)

Este repositorio sincroniza automáticamente tu plan de entrenamiento de Media Maratón (Lisboa 2027 y 2ª MM) con tu cuenta Básica de TrainingPeaks todos los días a las 10:00 AM (08:00 UTC).

## 📋 Pasos para publicar en tu GitHub:

1. **Crear un nuevo repositorio en GitHub:**
   - Ve a [GitHub](https://github.com/new).
   - Nombre del repositorio: `trainingpeaks-auto-sync` (o el que prefieras).
   - Selecciónalo como **Private** (Privado).
   - Haz clic en **Create repository**.

2. **Subir los archivos desde tu terminal:**
   Abre la aplicación Terminal en tu Mac y ejecuta:

   ```bash
   cd /Users/sema/.gemini/antigravity/scratch/github_actions_tp_sync
   git init
   git add .
   git commit -m "Initial commit - TP Auto Sync"
   git branch -M main
   git remote add origin https://github.com/TU_USUARIO/trainingpeaks-auto-sync.git
   git push -u origin main
   ```

3. **Añadir el Secret `TP_AUTH_COOKIE` en GitHub:**
   - En tu repositorio de GitHub, ve a **Settings** > **Secrets and variables** > **Actions**.
   - Haz clic en **New repository secret**.
   - **Name:** `TP_AUTH_COOKIE`
   - **Secret:** *(Copia y pega la clave de autenticación que te ha generado el asistente)*.
   - Haz clic en **Add secret**.

¡Listo! A partir de ese momento, **GitHub Actions ejecutará la sincronización todos los días a las 10:00 AM en sus servidores de forma 100% independiente de tu ordenador**.
