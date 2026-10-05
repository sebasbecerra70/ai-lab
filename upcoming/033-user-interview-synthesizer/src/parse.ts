// Parse transcripts into participant utterances with stable quote IDs.

export interface Participant {
  id: string;
  profile: string;
}

export interface Quote {
  id: string; // e.g. "P2-3": participant P2, 3rd utterance
  participant: string;
  text: string;
}

export function parseTranscripts(raw: string): { participants: Participant[]; quotes: Quote[] } {
  const participants: Participant[] = [];
  const quotes: Quote[] = [];
  let current: Participant | undefined;
  let n = 0;
  for (const line of raw.split(/\r?\n/)) {
    const header = line.match(/^===\s*(\w+)\s*\|\s*(.+)$/);
    if (header) {
      current = { id: header[1], profile: header[2].trim() };
      participants.push(current);
      n = 0;
      continue;
    }
    const said = line.match(/^(\w+):\s*(.+)$/);
    if (!current || !said || said[1] !== current.id) continue; // skip interviewer lines
    n += 1;
    quotes.push({ id: `${current.id}-${n}`, participant: current.id, text: said[2].trim() });
  }
  return { participants, quotes };
}
