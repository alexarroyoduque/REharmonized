import versionText from '../../../VERSION?raw';

const sources = import.meta.glob('../../../scripts/modules/*.py', {
  query: '?raw',
  import: 'default',
  eager: true,
});

export function installPythonModules(pyodide) {
  pyodide.FS.mkdirTree('/tmp/modules');
  pyodide.FS.writeFile('/tmp/VERSION', new TextEncoder().encode(versionText));
  for (const [path, source] of Object.entries(sources)) {
    const filename = path.slice(path.lastIndexOf('/') + 1);
    pyodide.FS.writeFile(`/tmp/modules/${filename}`, new TextEncoder().encode(source));
  }
}