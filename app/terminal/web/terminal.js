'use strict';
const terminal = new Terminal({cursorBlink:true, scrollback:3000, fontSize:13,
  fontFamily:'Menlo, Consolas, monospace', theme:{background:'#18202b',foreground:'#e1e6ef'},
  allowProposedApi:false, allowWindowOps:false});
const fit = new FitAddon.FitAddon();
terminal.loadAddon(fit);
terminal.open(document.getElementById('terminal'));
new QWebChannel(qt.webChannelTransport, channel => {
  const bridge = channel.objects.bridge;
  bridge.output_ready.connect(text => terminal.write(text));
  terminal.onData(text => bridge.input(text));
  terminal.onResize(size => bridge.resize_terminal(size.cols,size.rows));
  const resize = () => {try {fit.fit(); bridge.resize_terminal(terminal.cols,terminal.rows);} catch (_) {}};
  new ResizeObserver(resize).observe(document.getElementById('terminal'));
  terminal.attachCustomKeyEventHandler(event => {
    if (event.type === 'keydown' && (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'c' && terminal.hasSelection()) {
      // Native Qt clipboard copy is provided by the terminal panel's Copy action.
      return false;
    }
    return true;
  });
  bridge.ready(); resize(); terminal.focus();
});
