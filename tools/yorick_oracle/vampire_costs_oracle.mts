// Runs Yorick's own Vampire cost engine over a grid of cases and prints the
// answers as JSON, to serve as reference data for Horatio's pricing.
//
// Usage: node --experimental-strip-types vampire_costs_oracle.mts <path to BNSMETV1_VampireCosts.ts> <clan_rule.csv>
import { readFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'

const [costsPath, clanCsvPath] = process.argv.slice(2)
const costs = await import(pathToFileURL(costsPath).href)

// --- clan rules, straight from Yorick's data/bnsmetv1_clan_rule.csv ---------
function parseCsvLine(line: string): string[] {
  const out: string[] = []
  let cur = ''
  let quoted = false
  for (const ch of line) {
    if (ch === '"') quoted = !quoted
    else if (ch === ',' && !quoted) { out.push(cur); cur = '' }
    else cur += ch
  }
  out.push(cur)
  return out
}
const lines = readFileSync(clanCsvPath, 'utf8').trim().split('\n')
const header = parseCsvLine(lines[0])
const col = (name: string) => header.indexOf(name)
const clanRules = lines.slice(1).map((line) => {
  const row = parseCsvLine(line)
  const rec: Record<string, string | undefined> = {
    clan: row[col('clan')],
    discipline_1: row[col('discipline_1')] || undefined,
    discipline_2: row[col('discipline_2')] || undefined,
    discipline_3: row[col('discipline_3')] || undefined,
  }
  return { get: (attr: string) => rec[attr] }
})

// --- the grid -----------------------------------------------------------------
const DISCIPLINE_NAMES = ['Celerity', 'Dominate', 'Animalism', 'Thaumaturgy', 'Thaumaturgy: Path of Blood', 'Thaumaturgy: Lure of Flames']
const NAMES: Record<string, string[]> = {
  disciplines: DISCIPLINE_NAMES,
  elder_disciplines: ['Celerity', 'Animalism'],
  luminary_disciplines: ['Presence', 'Animalism'],
  techniques: ['Ward'],
  backgrounds: ['Generation', 'Resources'],
}
const CATEGORIES = [
  'attributes', 'focus_physicals', 'focus_mentals', 'focus_socials', 'health_levels',
  'willpower_sources', 'skills', 'lore_specializations', 'academics_specializations',
  'drive_specializations', 'linguistics_specializations', 'disciplines', 'techniques',
  'elder_disciplines', 'luminary_disciplines', 'rituals', 'extra_in_clan_disciplines', 'paths',
  'humanity', 'backgrounds', 'haven_specializations', 'contacts_specializations',
  'allies_specializations', 'sabbat_rituals', 'vampiric_texts',
  'influence_elite_specializations', 'influence_underworld_specializations', 'status_traits',
  'merits', 'flaws', 'no_such_category',
]
const CLAN_DEPENDENT = new Set(['disciplines', 'elder_disciplines', 'luminary_disciplines'])
const CLANS = ['Brujah', 'Tremere', 'Caitiff', 'Assamite: Sorcerer']
const EXTRAS = [[], ['Dominate']]
const GENERATIONS = [undefined, 0, 1, 2, 3, 4, 5, 6]
const VALUES = [0, 1, 2, 3, 4, 5, 6, 8, 10]
const FREE_VALUES = [0, 2]

const cases: unknown[] = []
for (const category of CATEGORIES) {
  const names = NAMES[category] ?? ['Example']
  const clans = CLAN_DEPENDENT.has(category) ? CLANS : ['Brujah']
  const extrasList = CLAN_DEPENDENT.has(category) ? EXTRAS : [[]]
  for (const name of names)
    for (const clan of clans)
      for (const extras of extrasList)
        for (const generation of GENERATIONS)
          for (const value of VALUES)
            for (const free_value of FREE_VALUES) {
              if (free_value > value) continue
              const character = {
                get: (attr: string) =>
                  attr === 'clan' ? clan
                  : attr === 'extra_in_clan_disciplines' ? extras.map((n) => ({ get: () => n }))
                  : undefined,
                // Yorick: `raw_generation || 1`.
                generation: () => generation || 1,
              }
              const trait = {
                get: (attr: string) =>
                  ({ category, name, value, free_value } as Record<string, unknown>)[attr],
                get_base_name: () => name.split(': ')[0],
              }
              const cost = costs.calculate_trait_cost(character, trait, clanRules)
              cases.push([category, name, clan, extras, generation ?? null, value, free_value, cost ?? null])
            }
}
process.stdout.write(JSON.stringify({
  columns: ['category', 'name', 'clan', 'extra_in_clan', 'generation', 'value', 'free_value', 'cost'],
  cases,
}))
