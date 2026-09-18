export function makeT(elementId) {
  let strings;
  return function t(key, values = {}) {
    strings ??= JSON.parse(document.getElementById(elementId).textContent);
    if (!(key in strings)) throw new Error(`no string ${key} on this page`);
    const text = strings[key];
    if (text === null) {
      const parts = [
        key,
        ...Object.entries(values).map(([name, value]) => `${name}=${value}`),
      ];
      return `⟦${parts.join(" ")}⟧`;
    }
    return text.replace(/\{\{|\}\}|\{(\w+)\}/g, (match, name) => {
      if (match === "{{") return "{";
      if (match === "}}") return "}";
      if (!(name in values))
        throw new Error(`${key} uses {${name}}, which the script does not pass`);
      return String(values[name]);
    });
  };
}
