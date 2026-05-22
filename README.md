# Poly AI Coworker — Asistente de Ventas de Alto Rendimiento

Poly es un agente de IA autónomo diseñado para transformar la interacción con clientes en canales como WhatsApp y Telegram. Construida sobre **LangGraph**, Poly no es solo un chatbot, sino una "compañera de trabajo" capaz de guiar a un cliente desde el descubrimiento de una necesidad hasta el cierre de una venta y el seguimiento post-venta.

## 🚀 Arquitectura "Poly 2.0"

Poly utiliza un grafo de estados dinámico que le permite tener un razonamiento fluido y resiliente:

- **Razonamiento Estructurado:** Un enrutador basado en LLM con salida determinística (Pydantic) que analiza el contexto y la inercia de la conversación para decidir el siguiente paso.
- **Marco de 3 Pilares:** Su comportamiento está regido por Principios Morales (Alma), una Constitución Política (Leyes) y un Contrato de Trabajo (Misión) definidos en `config/personality.yaml`.
- **RAG Avanzado:** Búsqueda semántica en tiempo real sobre el catálogo de productos (Qdrant).
- **Integración Multicanal:** 
  - **WhatsApp (Twilio):** Para atención directa a clientes.
  - **Telegram:** Hub de administración para el dueño del negocio.
- **Persistencia Profesional:** Memoria a largo plazo gestionada mediante PostgreSQL para reconocer a los clientes y sus preferencias meses después.

## 🛡️ Role-Based Access Control (RBAC)

La ejecución de herramientas está asegurada a través de un esquema estricto de roles:
- **`CUSTOMER_TOOLS`:** Herramientas globales para ventas y logística disponibles en todo momento (Consultas en catálogo Dropi, Verificación de datos, Creación y Cancelación segura de pedidos, y Escalación a Supervisor).
- **`ADMIN_TOOLS`:** Herramientas exclusivas para el rol de administrador desde Telegram. Permiten la manipulación autónoma de Poly sobre su propia arquitectura y la base de datos:
  - **Arquitecto:** Modificación y restauración de configuraciones y personalidad.
  - **CRM Memory:** Manipulación manual del historial y datos de clientes.
  - **Logística Avanzada:** Asignación de números de guía de envío e inmutabilidad de estado.
  - **BI & Analytics:** Extracción de KPIs y reportes financieros.

## 🛠️ Stack Tecnológico

- **Core:** Python 3.11+, LangChain, LangGraph.
- **Modelos:** GPT-4o Mini (Razonamiento), Gemini 2.0 Flash (Visión/Backup), Whisper (Voz).
- **Bases de Datos:** 
  - **PostgreSQL:** Memoria conversacional y CRM local.
  - **Qdrant:** Catálogo de productos vectorial.
  - **Supabase:** Registro central y control de pedidos en la nube.
- **Integraciones:** Dropi (Dropshipping), Twilio (WhatsApp), Telegram API.

## 📂 Estructura del Proyecto

```text
├── api/                # Endpoints de FastAPI para webhooks
├── channels/           # Adaptadores de WhatsApp y Telegram
├── config/             # Configuración de personalidad (YAML) y productos
├── core/
│   ├── brain/          # El "Cerebro": Grafos, Agentes, Enrutador, Selector y Herramientas
│   ├── knowledge/      # Motor RAG y búsqueda vectorial
│   └── memory/         # Modelos de base de datos y repositorios (CRM)
├── infrastructure/     # Notificaciones y utilidades core
├── integrations/       # Conexiones externas (Supabase, Dropi)
├── scripts/            # Herramientas de mantenimiento (Indexación, etc.)
├── poly_chat.py        # CLI para pruebas rápidas en terminal
└── telegram_runner.py  # Runner del panel administrativo
```

## ⚙️ Configuración Rápida

1. **Clonar y Preparar:**
   ```bash
   poetry install
   copy .env.example .env
   ```

2. **Indexar el Catálogo:**
   Edita `config/products.yaml` y ejecuta:
   ```bash
   python scripts/index_catalog.py
   ```

3. **Iniciar en Local:**
   ```bash
   python telegram_runner.py  # Para el panel de admin
   python poly_chat.py        # Para probar como cliente en consola
   ```

## 🎯 Filosofía de Ventas
Poly sigue un modelo de **Venta Consultiva**. Su prioridad es la empatía y la resolución de dudas. Solo cuando el cliente está listo, activa sus herramientas de cierre para recolectar datos y montar el pedido automáticamente en Supabase y plataformas de logística.

---
*Desarrollado con ❤️ para Vital Energy Shop.*
