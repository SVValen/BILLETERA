# AI Review Framework

Framework de revisión de código reutilizable basado en agentes de Claude Code.
Diseñado para proyectos Next.js + Supabase + Vercel.

## Para qué sirve

Ejecuta revisiones de código multi-dimensionales antes de mergear cambios:

- **Seguridad**: OWASP, RLS de Supabase, secrets, endpoints, multi-tenancy
- **Arquitectura**: Server/Client Components, separación de responsabilidades, performance, deuda técnica
- **Calidad**: casos borde, concurrencia, robustez, cobertura de tests
- **Contexto**: mantiene el `AGENTS.md` del proyecto actualizado con cada cambio

## Stack soportado

| Tecnología | Soporte |
|---|---|
| Next.js 13+ App Router | ✓ Nativo |
| Supabase (PostgreSQL + Auth + Storage) | ✓ Nativo |
| Vercel (hosting + crons) | ✓ Nativo |
| TypeScript | ✓ Nativo |
| MercadoPago / Stripe (pagos) | ✓ Incluido en security-reviewer |
| Telegram Bot API | ✓ Incluido en security-reviewer |
| Meta Cloud API (WhatsApp) | ✓ Incluido en security-reviewer |

## Estructura

```
ai-review-framework/
├── agents/
│   ├── security-reviewer.md      # OWASP, RLS, secrets, endpoints
│   ├── architecture-reviewer.md  # Next.js patterns, SOLID, performance
│   ├── qa-reviewer.md            # Edge cases, concurrencia, robustez
│   ├── orchestrator.md           # Consolida hallazgos y emite veredicto
│   ├── context-updater.md        # Mantiene AGENTS.md actualizado
│   └── snapshot-architect.md     # Genera y mantiene ARCHITECTURE.md
├── checklists/
│   ├── supabase.md               # RLS, clients, storage, queries
│   ├── nextjs.md                 # App Router, caché, Server Actions
│   └── security.md               # OWASP Top 10 adaptado al stack
└── commands/
    ├── review.md                 # Orquesta la revisión completa
    ├── update-context.md         # Actualiza el contexto de negocio (AGENTS.md)
    ├── snapshot.md                # Genera el mapa técnico del proyecto (ARCHITECTURE.md)
    ├── install.md                 # Instala el framework de punta a punta (remote, subtree, wrappers, AGENTS.md)
    └── sync-commands.md           # Sincroniza wrappers después de un subtree pull
```

## Integración en un proyecto

### Bootstrap (sin crear nada a mano)

Abrí Claude Code en el proyecto destino y pedile directamente, en un solo mensaje:

```
Instalá el framework ai-review-framework desde
https://github.com/SVValen/ai-review-framework.git en este proyecto.
```

No hace falta crear ningún archivo vos mismo: Claude no necesita que el wrapper
de `/install` exista de antemano para seguir esas instrucciones — puede leer
`commands/install.md` de este repo y ejecutar sus pasos directamente. Va a:

1. Verificar que el working tree esté limpio y confirmar contigo antes de tocar git.
2. Agregar el remote y el subtree (`.review/`).
3. Crear todos los wrappers en `.claude/commands/` (incluido el de `/install`, para
   que en el futuro también puedas invocarlo como slash command normal).
4. Crear `.claude/agents/` y `.claude/reports/`.
5. Explorar el codebase (`package.json`, `README.md`, `.env.example`, estructura de
   carpetas) y proponerte un `AGENTS.md`, mostrándotelo antes de escribirlo.
6. Crear `CLAUDE.md` con `@AGENTS.md`.
7. Ofrecerte correr `/snapshot` para generar `ARCHITECTURE.md` en el mismo momento.

Cada paso que modifica el repo o sobrescribe un archivo existente pide confirmación
explícita antes de aplicarse — no corre nada destructivo en silencio.

Una vez instalado, para sesiones futuras (o si preferís invocarlo como slash command)
alcanza con escribir `/install` directamente, ya que el wrapper queda creado.

### Instalación manual (referencia, paso a paso)

Si por algún motivo preferís hacer cada paso vos mismo en lugar de pedírselo a Claude:

```bash
git remote add ai-review-framework https://github.com/SVValen/ai-review-framework.git
git subtree add --prefix=.review ai-review-framework main --squash
```

Crear `.claude/commands/review.md`:

```markdown
# /review

Lee `.review/commands/review.md` y ejecutá sus instrucciones exactamente.

Los agentes están en `.review/agents/`.
Los checklists están en `.review/checklists/`.
El contexto del proyecto está en `AGENTS.md`.
```

Crear `.claude/commands/update-context.md`:

```markdown
# /update-context

Lee `.review/commands/update-context.md` y ejecutá sus instrucciones exactamente.

Los agentes están en `.review/agents/`.
El contexto del proyecto está en `AGENTS.md`.
```

Crear `.claude/commands/snapshot.md`:

```markdown
# /snapshot

Lee `.review/commands/snapshot.md` y ejecutá sus instrucciones exactamente.

Los agentes están en `.review/agents/`.
El contexto del proyecto está en `AGENTS.md`.
```

Crear `AGENTS.md` en la raíz del proyecto con esta estructura:

```markdown
# Contexto de Proyecto — [NOMBRE]
> Leer al inicio de cada sesión de trabajo y antes de ejecutar /review.

## Descripción
[Qué hace el proyecto]

## Stack
[Tecnologías usadas]

## Flujos críticos
[Los flujos principales del sistema]

## Reglas de negocio invariantes
[Reglas que nunca deben romperse]

## Variables de entorno críticas (nunca exponer al cliente)
[Lista de variables sensibles]
```

Crear `CLAUDE.md` en la raíz:

```markdown
@AGENTS.md
```

Crear carpetas de soporte:

```bash
mkdir -p .claude/agents .claude/reports
```

La carpeta `.claude/agents/` es para agentes de dominio específicos del proyecto
(lógica de negocio, reglas de pricing, etc.) que complementan los agentes genéricos del framework.

## Comandos disponibles

### `/review`

Revisión completa antes de mergear. Ejecuta todos los agentes en secuencia y emite un veredicto.

```
/review                          # Revisa el diff actual
/review [archivo o carpeta]      # Revisa un área específica
/review --area [descripción]     # Describís vos qué revisar
/review --security-only          # Solo seguridad
/review --quick                  # Solo security + QA
```

**Veredictos posibles:**
- `APROBADO` — sin críticos ni altos
- `APROBADO CON OBSERVACIONES` — sin críticos, altos aceptados conscientemente
- `REQUIERE CAMBIOS` — hay altos que deben resolverse
- `BLOQUEADO` — hay al menos un crítico

### `/update-context`

Actualiza `AGENTS.md` después de una feature o cambio importante.

```
/update-context                  # Analiza el último commit
/update-context --last 3         # Analiza los últimos N commits
/update-context --area [texto]   # Describís vos el cambio
```

Propone los cambios antes de aplicarlos. Requiere confirmación explícita.

### `/snapshot`

Genera o actualiza `ARCHITECTURE.md` — el mapa técnico del proyecto.
Cubre: archivos clave, patrones del proyecto, decisiones de arquitectura y trabajo en curso.
Una vez generado, Claude lo carga automáticamente en cada sesión sin explorar el codebase.

```
/snapshot            # Genera ARCHITECTURE.md completo
/snapshot --update   # Actualiza solo las secciones afectadas por cambios recientes
```

### `/install`

Instala el framework de punta a punta: remote, subtree, wrappers de comandos,
carpetas de soporte, `AGENTS.md` y `CLAUDE.md`. Ver "Bootstrap" más arriba —
la primera vez no hace falta que exista el wrapper, se le puede pedir directo a Claude.

```
/install
/install https://github.com/usuario/fork.git   # remote propio o fork
```

Explora el codebase para proponer un `AGENTS.md` inicial y muestra el contenido antes
de escribirlo. Cada acción sobre git o sobre archivos existentes pide confirmación.

### `/sync-commands`

Detecta comandos nuevos del framework sin wrapper local y los crea. Correr después
de cada `git subtree pull`.

## Flujo de trabajo recomendado

### Primera vez en un proyecto

```
1. /snapshot         ← analiza el codebase y genera ARCHITECTURE.md
                       (Claude agrega @ARCHITECTURE.md a CLAUDE.md automáticamente)
2. Listo — las próximas sesiones arrancan con contexto completo
```

### Trabajo diario

```
1. Implementás una feature
2. /update-context   ← actualiza AGENTS.md con nuevas reglas o flujos
3. /review           ← revisa el diff antes de mergear
4. Merge
```

### Después de una refactorización

```
1. /snapshot --update  ← actualiza solo las secciones del mapa que cambiaron
```

### Qué carga Claude al inicio de cada sesión

```
CLAUDE.md
  @AGENTS.md          ← negocio: reglas, flujos, invariantes, variables críticas
  @ARCHITECTURE.md    ← técnico: archivos clave, patrones, decisiones, trabajo en curso
```

Con ambos archivos al día, Claude no necesita explorar el proyecto desde cero.
El contexto persiste entre sesiones sin esfuerzo manual.

## Actualizar el framework en un proyecto

Cuando el framework recibe mejoras:

```bash
git subtree pull --prefix=.review ai-review-framework main --squash
```

## Agentes de dominio por proyecto

Los agentes genéricos del framework cubren seguridad, arquitectura y QA.
Para lógica específica del negocio (pricing, flujos de pago, reglas de membresía),
podés agregar agentes propios en `.claude/agents/` del proyecto.

El `/review` los detecta automáticamente y los ejecuta como paso adicional.

Ejemplo de agente de dominio: `.claude/agents/biz-validator.md` con las reglas
de negocio específicas del producto.
