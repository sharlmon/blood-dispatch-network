<template>
  <div class="cells" aria-hidden="true">
    <i class="c c1" /><i class="c c2" /><i class="c c3" /><i class="c c4" /><i class="c c5" />
  </div>
</template>

<style scoped>
.cells { position: fixed; inset: 0; overflow: hidden; pointer-events: none; z-index: 0; }
.c {
  position: absolute; display: block; border-radius: 50%;
  background: radial-gradient(ellipse at 35% 30%, #e8665f 0%, #b3171e 55%, #8c1015 100%);
  box-shadow: inset -6px -8px 14px rgba(70, 5, 10, 0.35);
  animation: drift 18s ease-in-out infinite;
}
.c1 { width: 120px; height: 66px; left: -30px; top: 8%; transform: rotate(-28deg); filter: blur(1px); }
.c2 { width: 90px; height: 50px; right: 6%; top: 34%; transform: rotate(32deg); filter: blur(3px); opacity: 0.8; animation-duration: 22s; animation-delay: -4s; }
.c3 { width: 60px; height: 34px; left: 38%; bottom: 10%; transform: rotate(-14deg); filter: blur(5px); opacity: 0.6; animation-duration: 16s; animation-delay: -8s; }
.c4 { width: 150px; height: 84px; right: -50px; bottom: 22%; transform: rotate(18deg); filter: blur(2px); opacity: 0.85; animation-duration: 26s; animation-delay: -2s; }
.c5 { width: 46px; height: 26px; left: 12%; top: 58%; transform: rotate(40deg); filter: blur(4px); opacity: 0.55; animation-duration: 20s; animation-delay: -11s; }
@keyframes drift {
  0%, 100% { translate: 0 0; rotate: 0deg; }
  50% { translate: 14px -22px; rotate: 8deg; }
}
</style>
