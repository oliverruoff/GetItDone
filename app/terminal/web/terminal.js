'use strict';
const terminal = new Terminal({cursorBlink:true, scrollback:3000, fontSize:13,
  fontFamily:'Menlo, Consolas, monospace', theme:{background:'#18202b',foreground:'#e1e6ef'},
  windowsPty: navigator.userAgent.includes('Windows') ? {backend:'conpty'} : undefined,
  allowProposedApi:false, allowWindowOps:false});
const fit = new FitAddon.FitAddon();
terminal.loadAddon(fit);
terminal.open(document.getElementById('terminal'));
new QWebChannel(qt.webChannelTransport, channel => {
  const bridge = channel.objects.bridge;
  bridge.output_ready.connect(text => terminal.write(text));
  terminal.onData(text => bridge.input(text));
  terminal.onResize(size => bridge.resize_terminal(size.cols,size.rows));
  let frame;
  const resize = () => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      const element = document.getElementById('terminal');
      if (!element.clientWidth || !element.clientHeight) return;
      try {fit.fit(); bridge.resize_terminal(terminal.cols,terminal.rows); terminal.refresh(0,terminal.rows-1);} catch (_) {}
    });
  };
  new ResizeObserver(resize).observe(document.getElementById('terminal'));
  document.fonts.ready.then(resize);
  window.addEventListener('focus', resize);
  document.addEventListener('visibilitychange', resize);
  terminal.attachCustomKeyEventHandler(event => {
    if (event.type === 'keydown' && event.shiftKey && ['PageUp','PageDown'].includes(event.key)) {
      terminal.scrollPages(event.key === 'PageUp' ? -1 : 1);
      return false;
    }
    if (event.type === 'keydown' && (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'c' && terminal.hasSelection()) {
      // Native Qt clipboard copy is provided by the terminal panel's Copy action.
      return false;
    }
    return true;
  });
  document.getElementById('terminal').addEventListener('wheel', event => {
    if (event.shiftKey) {
      terminal.scrollLines(Math.sign(event.deltaY) * 3);
      event.preventDefault(); event.stopPropagation();
    }
  }, {capture:true, passive:false});
  bridge.ready(); resize(); terminal.focus();
});
