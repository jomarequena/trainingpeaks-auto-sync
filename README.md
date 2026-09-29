# 🚀 TrainingPeaks Auto Sync (GitHub Actions)

Este repositorio sincroniza automáticamente tu plan de entrenamiento de Media Maratón (Lisboa 2027 y 2ª MM) con tu cuenta Básica de TrainingPeaks todos los días cada 30 minutos entre las 05:00 y las 08:00 UTC (incluidas). En España peninsular, esta ventana corresponde a las 06:00–09:00 en horario de invierno (CET) y a las 07:00–10:00 en horario de verano (CEST); GitHub Actions programa el horario en UTC y no lo ajusta al cambio de hora local. GitHub Actions puede retrasar o no ejecutar una ejecución programada, así que estos reintentos aumentan las oportunidades de sincronizar, pero no garantizan que se ejecute.

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

3. **Añadir los Secrets necesarios en GitHub:**
   - En tu repositorio de GitHub, ve a **Settings** > **Secrets and variables** > **Actions**.
   - Haz clic en **New repository secret**.
   - **Name:** `TP_AUTH_COOKIE`
   - **Secret:** *(Copia y pega la clave de autenticación que te ha generado el asistente)*.
   - Haz clic en **Add secret** y repite el proceso para el segundo secret:
   - **Name:** `TP_ATHLETE_ID`
   - **Secret:** el ID numérico de atleta de tu cuenta TrainingPeaks.

¡Listo! A partir de ese momento, **GitHub Actions intentará sincronizar cada 30 minutos desde las 05:00 hasta las 08:00 UTC, ambos horarios incluidos, de forma independiente de tu ordenador**. La ventana en España peninsular será las 06:00–09:00 en invierno (CET) y las 07:00–10:00 en verano (CEST); GitHub Actions no ajusta el horario UTC al cambio de hora local. Los horarios programados de GitHub Actions no están garantizados, pero las ejecuciones adicionales ofrecen más oportunidades si se pierde una.

## Prevención de duplicados

Antes de crear un workout para un día del plan, la sincronización consulta TrainingPeaks. Si ya existe cualquier workout ese día —planificado o completado—, lo omite y lo registra en `synced_log.json`. Si no puede consultar TrainingPeaks o interpretar la respuesta, no crea el workout y la ejecución termina con error para que el problema sea visible.

# trainingpeaks-auto-sync
