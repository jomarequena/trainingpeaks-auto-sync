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

## Plan de entrenamiento 2026–2027

El calendario empieza desde cero el martes 3 de noviembre de 2026 con CACO (20–25 minutos por sesión, alternando trote fácil y caminata). Los minutos crecen pronto y de forma gradual: tres carreras los martes, jueves y sábados, bicicleta fácil los miércoles, semanas de descarga y un fondo máximo de 105 minutos antes del test. Cada entrenamiento de carrera especifica bloques cuya suma coincide con la duración programada. Incluye rangos de ritmo orientativos para los rodajes fáciles; como no hay una marca reciente para calibrar las zonas, manda el esfuerzo conversacional y no hay que acelerar para alcanzar esos rangos. Las series cortas se pautan por esfuerzo y recuperación, no por ritmo GPS. La media maratón del 7 de marzo de 2027 está programada como test controlado, no a tope, seguida de recuperación; la carrera A es el 4 de abril. El objetivo de 1h45 (4:59 min/km) es aspiracional y no está garantizado, especialmente al retomar desde cero; la progresión prioriza llegar sano y debe ajustarse si aparece dolor o fatiga inusual.

Los entrenamientos de carrera y bicicleta se envían a TrainingPeaks con bloques temporizados y objetivos de intensidad relativa (% del ritmo umbral o FTP). Como no hay un test reciente para personalizar los umbrales, esos objetivos son rangos amplios y debe prevalecer el esfuerzo fácil indicado. Las dos medias maratones se dejan como eventos guiados por su descripción, sin imponer una estructura de ritmo no calibrada.

El calendario contiene además una sesión CACO de prueba de 20 minutos para el 29 de octubre de 2026, destinada a comprobar la sincronización de intervalos estructurados; la protección de duplicados evita crear otra sesión si ya existe un entrenamiento ese día.
