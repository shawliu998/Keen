const generatedModePrefix = /^(study|teach|review|plan):\s*/i;

export function displayLearningTitle(value: string): string {
  const title = value.trim();
  const veryWeak = title.match(/^study very weak concept:\s*(.+)$/i);
  if (veryWeak?.[1]) return `Strengthen ${veryWeak[1].trim()}`;

  const weak = title.match(/^study weak concept:\s*(.+)$/i);
  if (weak?.[1]) return `Review ${weak[1].trim()}`;

  const misconception = title.match(/^address misconception:\s*(.+)$/i);
  if (misconception?.[1]) return `Resolve ${misconception[1].trim()}`;

  const resumed = title.match(/^resume study session:\s*(.+)$/i);
  if (resumed?.[1]) return displayLearningTitle(resumed[1]);

  const normalized = title.replace(generatedModePrefix, "").trim();
  return normalized || title;
}

export function learningTitlesMatch(left: string, right: string): boolean {
  return displayLearningTitle(left).toLocaleLowerCase() === displayLearningTitle(right).toLocaleLowerCase();
}
