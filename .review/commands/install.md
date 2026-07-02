# /install — Instalar el framework en el proyecto actual

Instala el framework completo de punta a punta: remote, subtree, wrappers de comandos,
`AGENTS.md`, `CLAUDE.md` y carpetas de soporte. Es el único paso manual real: crear
este wrapper una vez (ver "Bootstrap" en el README). A partir de ahí, todo lo demás
lo hace este comando.

## Uso

```
/install
/install https://github.com/usuario/ai-review-framework.git   # remote propio o fork
```

Si no se pasa URL, se usa `https://github.com/SVValen/ai-review-framework.git` por defecto.

## Paso 0 — Remote y subtree

```bash
ls .review 2>/dev/null
```

Si `.review/` ya existe: saltear a Paso 1.

Si no existe:

1. Verificá que el repo destino no tenga cambios sin commitear (`git status`).
   `git subtree add` falla o mezcla cosas raras sobre un working tree sucio —
   si hay cambios pendientes, avisá al usuario y pedile que commitee o haga stash antes de seguir.
2. Mostrale al usuario los comandos que vas a correr y pedí confirmación (esto agrega
   un remote y trae historia externa al repo, es una acción que vale la pena confirmar):

```bash
git remote add ai-review-framework [URL]
git subtree add --prefix=.review ai-review-framework main --squash
```

   Si el remote `ai-review-framework` ya existe apuntando a otra URL, avisá y preguntá
   si continuar con el remote existente o abortar.

3. Con confirmación, ejecutá ambos comandos.

## Paso 1 — Crear wrappers de comandos

```bash
ls .review/commands/
```

Para cada archivo `.md` en `.review/commands/` (incluido `install.md`, así el propio
comando queda auto-instalado para el próximo `subtree pull`), verificá si existe el
wrapper correspondiente en `.claude/commands/`. Para cada uno que falte, creá
`.claude/commands/[nombre].md` con este contenido exacto:

```
# /[nombre]

Lee `.review/commands/[nombre].md` y ejecutá sus instrucciones exactamente.

Los agentes están en `.review/agents/`.
Los checklists están en `.review/checklists/`.
El contexto del proyecto está en `AGENTS.md`.
```

## Paso 2 — Crear carpetas de soporte

```bash
mkdir -p .claude/agents .claude/reports
```

Si `.claude/agents/` ya tiene contenido, no lo toques — es donde viven los agentes
de dominio específicos del proyecto.

## Paso 3 — Generar `AGENTS.md`

Si ya existe `AGENTS.md`, mostrale su contenido actual al usuario y preguntá si
querés regenerarlo o dejarlo como está. Si el usuario no confirma, salteá este paso.

Si no existe (o el usuario confirmó regenerar):

1. Adoptá la identidad definida en `.review/agents/installer.md`.
2. Explorá el proyecto siguiendo el proceso descripto ahí: `package.json`, `README.md`,
   `.env.example`, estructura de directorios (máx. 2 niveles), patrones de validación repetidos.
3. Generá el contenido completo de `AGENTS.md`.
4. Mostrá el contenido propuesto al usuario, señalando qué secciones quedaron con
   placeholders pendientes de completar a mano.
5. Con confirmación del usuario, escribí `AGENTS.md` en la raíz del proyecto.

## Paso 4 — Crear o actualizar `CLAUDE.md`

Si no existe `CLAUDE.md`, creálo con:

```
@AGENTS.md
```

Si ya existe pero no referencia `@AGENTS.md`, agregá esa línea al principio sin
tocar el resto del contenido.

## Paso 5 — Ofrecer el snapshot

Preguntá si querés correr `/snapshot` ahora mismo para generar `ARCHITECTURE.md`.
Si el usuario confirma, ejecutalo como paso final de esta misma sesión.

## Paso 6 — Reportar resultado

Mostrá un resumen:

```
## Instalación completada

- Remote + subtree: [creado / ya existía]
- Wrappers creados: [lista] (ya existentes: [lista])
- Carpetas de soporte: .claude/agents/, .claude/reports/ ✓
- AGENTS.md: [generado / actualizado / sin cambios — motivo]
- CLAUDE.md: [creado / ya referenciaba AGENTS.md]
- ARCHITECTURE.md: [generado / salteado]
```

## Reglas de comportamiento

- Nunca sobrescribas `AGENTS.md` o `CLAUDE.md` existentes sin mostrar el contenido
  propuesto y pedir confirmación explícita primero.
- El paso 0 modifica el repo (remote + subtree) — confirmalo con el usuario antes
  de ejecutarlo, igual que cualquier otra acción de git con efectos persistentes.
- Si el proyecto no tiene `package.json` (no es Node/Next.js), avisá que el framework
  está pensado para ese stack y preguntá si continuar igual con una exploración genérica.
