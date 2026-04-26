// audio.js — enable per-post "Read aloud" buttons when a pre-rendered clip exists.
// Loads audio_manifest.json once per page. Falls back to browser SpeechSynthesis
// when no clip is available.
(function () {
  var manifestPromise = null;
  function manifest() {
    if (!manifestPromise) {
      // Resolve manifest path relative to site root. Pages in themes/ or timeline/
      // need "../data/audio_manifest.json"; the root pages need "data/...".
      var path = location.pathname.match(/\/(themes|timeline)\//)
        ? "../data/audio_manifest.json"
        : "data/audio_manifest.json";
      manifestPromise = fetch(path)
        .then(function (r) { return r.ok ? r.json() : { entries: {} }; })
        .catch(function () { return { entries: {} }; });
    }
    return manifestPromise;
  }

  function prefixAudio() {
    return location.pathname.match(/\/(themes|timeline)\//) ? "../audio/" : "audio/";
  }

  var currentAudio = null;

  function speakBrowser(text) {
    if (!("speechSynthesis" in window)) return;
    var u = new SpeechSynthesisUtterance(text);
    u.rate = 1.0;
    u.pitch = 1.0;
    speechSynthesis.cancel();
    speechSynthesis.speak(u);
  }

  function onClick(btn) {
    var pid = btn.dataset.postId;
    var url = btn.dataset.audioUrl;
    if (currentAudio) { currentAudio.pause(); currentAudio = null; }

    if (url) {
      currentAudio = new Audio(url);
      currentAudio.play().catch(function () {
        // fall back to browser TTS if playback fails
        var textEl = btn.closest(".post-card").querySelector(".text");
        if (textEl) speakBrowser(textEl.textContent);
      });
    } else {
      var textEl = btn.closest(".post-card").querySelector(".text");
      if (textEl) speakBrowser(textEl.textContent);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    manifest().then(function (m) {
      var entries = (m && m.entries) || {};
      var buttons = document.querySelectorAll(".read-aloud[data-post-id]");
      buttons.forEach(function (btn) {
        var pid = btn.dataset.postId;
        if (entries[pid]) {
          btn.dataset.audioUrl = prefixAudio() + pid + ".mp3";
          btn.title = "Plays a pre-rendered Trump-voice clip";
          btn.disabled = false;
          btn.textContent = "▶ Trump voice";
          btn.classList.add("has-clone");
        } else {
          // Browser-TTS fallback available to anyone
          btn.title = "Uses your browser's voice (no Trump clone rendered for this post)";
          btn.disabled = false;
          btn.textContent = "🔊 Browser voice";
          btn.classList.add("no-clone");
        }
        btn.addEventListener("click", function (e) { e.preventDefault(); onClick(btn); });
      });
    });
  });
})();
