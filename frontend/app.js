(function () {
  const statusEl = document.getElementById("status");
  const bufferMetricEl = document.getElementById("buffer-metric");
  const sessionMetricEl = document.getElementById("session-metric");
  const dispatchMetricEl = document.getElementById("dispatch-metric");
  const callerStreamEl = document.getElementById("caller-stream");
  const agentStreamEl = document.getElementById("agent-stream");
  const cleanedStreamEl = document.getElementById("cleaned-stream");
  const eventLogEl = document.getElementById("event-log");
  const snapshotGridEl = document.getElementById("snapshot-grid");
  const labelChipsEl = document.getElementById("label-chips");
  const severityHeroEl = document.getElementById("severity-hero");
  const severityScoreEl = document.getElementById("severity-score");
  const severitySubtextEl = document.getElementById("severity-subtext");
  const operatorReportEl = document.getElementById("operator-report");
  const takeoverBtn = document.getElementById("takeover-btn");
  const triagePanelEl = document.getElementById("triage-panel");
  const ticketPanelEl = document.getElementById("ticket-panel");
  const toolChainEl = document.getElementById("tool-chain");
  const toolLogEl = document.getElementById("tool-log");
  const memoryPanelEl = document.getElementById("memory-panel");
  const mapStatusEl = document.getElementById("map-status");
  const servicePanelEl = document.getElementById("service-panel");
  const connectBtn = document.getElementById("connect-btn");
  const disconnectBtn = document.getElementById("disconnect-btn");
  const clearBtn = document.getElementById("clear-btn");
  const dispatchModeSelect = document.getElementById("dispatch-mode-select");

  let ws = null;
  let player = null;
  let sessionId = null;
  let sessionStartedAt = null;
  let reportSent = false;
  let userTranscriptChunks = [];
  let agentTranscriptChunks = [];
  let userTranscripts = [];
  let agentTranscripts = [];
  let pendingUserChunks = [];
  let pendingAgentChunks = [];
  let eventEntries = [];
  let maxBufferMs = 0;
  let sessionPollHandle = null;
  let syncHandle = null;
  let latestSession = null;
  let map = null;
  let mapMarker = null;
  let lastMapAnimationKey = null;
  let interruptCount = 0;
  let lastAdaptiveAt = 0;
  let recoveryModeArmed = false;
  let assistantTurnActive = false;
  let pendingTriageUpdate = null;
  let pendingLedgerUpdate = null;
  let pendingDispatchUpdate = null;
  let triageSyncTimeout = null;
  let userFinalizeHandle = null;
  let latestTriageContext = null;
  let latestLedgerContext = null;
  let latestDispatchContext = null;
  let lastTriageVersionSent = 0;
  let lastLedgerVersionSent = 0;
  let lastDispatchVersionSent = 0;
  let lastRescueIndexSeen = -1;
  let lastActiveTranscriptProvider = "gradium";
  let humanTakeoverEngaged = false;
  let stickySummaryText = null;
  let pendingHandoffResumePrompt = null;
  let currentAudioConfig = {
    pcm: false,
    pcm_input: false,
    sample_rate: 48000,
    channels: 1,
  };
  let pcmCaptureSource = null;
  let pcmCaptureNode = null;
  let pcmCaptureSink = null;
  let pcmCapturePending = [];
  const SHORT_FINALIZE_DELAY_MS = 180;
  const DEFAULT_FINALIZE_DELAY_MS = 450;
  const DISPATCH_MODE_STORAGE_KEY = "dispatchMode";
  const HANDOFF_RESUME_PROMPT = "What is your status now?";

  function normalizeDispatchMode(value) {
    return String(value || "slm").trim().toLowerCase() === "llm_only" ? "llm_only" : "slm";
  }

  function dispatchModeLabel(value) {
    return normalizeDispatchMode(value) === "llm_only" ? "LLM only" : "SLM + LLM";
  }

  function getSelectedDispatchMode() {
    return normalizeDispatchMode(dispatchModeSelect?.value);
  }

  function setStatus(text, kind) {
    statusEl.textContent = text;
    statusEl.className = `status ${kind}`;
  }

  function now() {
    return new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }

  function escapeHtml(text) {
    return String(text)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }

  function titleCase(value) {
    return String(value || "")
      .replaceAll("_", " ")
      .toLowerCase()
      .replace(/\b\w/g, (match) => match.toUpperCase());
  }

  function latestTranscriptText(items, count = 3) {
    return (items || [])
      .slice(-count)
      .map((item) => item.text)
      .filter(Boolean)
      .join(" ")
      .trim();
  }

  function humanizeField(field) {
    const aliases = {
      victim_breathing: "Breathing status",
      victim_bleeding: "Bleeding status",
      victim_conscious: "Consciousness",
      victim_count: "Victim count",
      caller_safe: "Caller safety",
      issue_type: "Incident type",
      priority: "Priority",
      location: "Location",
    };
    return aliases[field] || titleCase(field);
  }

  function severityBand(score) {
    if (score >= 86) return "red";
    if (score >= 61) return "orange";
    if (score >= 31) return "amber";
    return "green";
  }

  function severityHeadline(score) {
    if (score >= 86) return "Human Required Now";
    if (score >= 61) return "Human Intervention Requested";
    if (score >= 31) return "Human Review Recommended";
    return "Autonomous Handling";
  }

  function appendEntry(target, klass, who, text) {
    const entry = document.createElement("article");
    entry.className = `entry ${klass}`;
    entry.innerHTML = `
      <div class="meta">
        <span class="who">${escapeHtml(who)}</span>
        <span>${now()}</span>
      </div>
      <div class="body"></div>
    `;
    entry.querySelector(".body").textContent = text;
    target.appendChild(entry);
    target.scrollTop = target.scrollHeight;
  }

  function joinTranscriptChunks(items) {
    return items
      .map((item) => item.text)
      .filter(Boolean)
      .join(" ")
      .replace(/\s+([,.;:!?])/g, "$1")
      .replace(/\s{2,}/g, " ")
      .trim();
  }

  function cleanCallerTranscript(rawText) {
    if (!rawText) return "";
    let cleaned = ` ${rawText} `;
    cleaned = cleaned.replace(/\b(can you hear me\??\s*)+/gi, " ");
    cleaned = cleaned.replace(/\b(uh|um|erm|hmm|ah)\b/gi, " ");
    cleaned = cleaned.replace(/\b(\w+)(\s+\1\b)+/gi, "$1");
    cleaned = cleaned.replace(/\s+([,.;:!?])/g, "$1");
    cleaned = cleaned.replace(/\s{2,}/g, " ").trim();

    const sentences = cleaned
      .split(/(?<=[.!?])\s+/)
      .map((item) => item.trim())
      .filter(Boolean);
    const deduped = [];
    for (const sentence of sentences) {
      if (!deduped.length || deduped[deduped.length - 1].toLowerCase() !== sentence.toLowerCase()) {
        deduped.push(sentence);
      }
    }
    return deduped.join(" ").trim();
  }

  function renderDialogueStreams() {
    const callerRaw = joinTranscriptChunks(userTranscriptChunks);
    const agentRaw = joinTranscriptChunks(agentTranscriptChunks);
    const callerCleaned = cleanCallerTranscript(callerRaw);

    callerStreamEl.textContent = callerRaw || "Waiting for caller audio.";
    agentStreamEl.textContent = agentRaw || "Waiting for dispatcher audio.";
    cleanedStreamEl.textContent = callerCleaned || "Waiting for cleaned caller text.";
  }

  function logEvent(text, kind = "event") {
    appendEntry(eventLogEl, kind, kind === "error" ? "Error" : "Event", text);
    eventEntries.push({
      at: new Date().toISOString(),
      kind,
      text,
    });
  }

  function clearTranscriptBuffers() {
    if (userFinalizeHandle) {
      clearTimeout(userFinalizeHandle);
      userFinalizeHandle = null;
    }
    pendingUserChunks = [];
    pendingAgentChunks = [];
  }

  function finalizePendingUser(reason = "silence") {
    if (userFinalizeHandle) {
      clearTimeout(userFinalizeHandle);
      userFinalizeHandle = null;
    }
    if (!pendingUserChunks.length) return;
    const text = joinTranscriptChunks(pendingUserChunks);
    pendingUserChunks = [];
    if (!text) return;
    userTranscripts.push({
      at: new Date().toISOString(),
      text,
      reason,
    });
    scheduleTriageSync();
  }

  function finalizePendingAgent(reason = "turn_end") {
    if (!pendingAgentChunks.length) return;
    const text = joinTranscriptChunks(pendingAgentChunks);
    pendingAgentChunks = [];
    if (!text) return;
    agentTranscripts.push({
      at: new Date().toISOString(),
      text,
      reason,
    });
    scheduleTriageSync();
  }

  function scheduleUserFinalize(latestText) {
    if (userFinalizeHandle) {
      clearTimeout(userFinalizeHandle);
    }
    const pendingText = joinTranscriptChunks(pendingUserChunks);
    const wordCount = pendingText ? pendingText.split(/\s+/).filter(Boolean).length : 0;
    const endsWithBoundary = /[.!?,]$/.test((latestText || "").trim());
    const delay = endsWithBoundary && wordCount >= 3 ? SHORT_FINALIZE_DELAY_MS : DEFAULT_FINALIZE_DELAY_MS;
    userFinalizeHandle = setTimeout(() => {
      userFinalizeHandle = null;
      finalizePendingUser("silence");
    }, delay);
  }

  function logTranscript(text, isUser) {
    if (!text || !String(text).trim()) return;
    if (!isUser && !humanTakeoverEngaged && pendingHandoffResumePrompt) {
      pendingHandoffResumePrompt = null;
    }
    const item = {
      at: new Date().toISOString(),
      text,
    };
    if (isUser) {
      userTranscriptChunks.push(item);
      pendingUserChunks.push(item);
      scheduleUserFinalize(text);
    } else {
      agentTranscriptChunks.push(item);
      pendingAgentChunks.push(item);
    }
    renderDialogueStreams();
  }

  function getWsUrl() {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.host}/ws`;
  }

  function currentDispatchContextForWire() {
    if (!latestDispatchContext) return null;
    return { ...latestDispatchContext };
  }

  function currentLedgerContextForWire() {
    if (!latestLedgerContext) return null;
    return { ...latestLedgerContext };
  }

  function raiseAdaptivePatience(reason) {
    const nowMs = Date.now();
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (nowMs - lastAdaptiveAt < 4000) return;
    interruptCount += 1;
    lastAdaptiveAt = nowMs;
    recoveryModeArmed = true;
    ws.send(
      JSON.stringify({
        type: "config",
        reason,
        interrupt_count: interruptCount,
        interruption_recovery: true,
        triage_context: latestTriageContext,
        ledger_context: currentLedgerContextForWire(),
        dispatch_context: currentDispatchContextForWire(),
        human_takeover_active: humanTakeoverEngaged,
        handoff_recovery_prompt: pendingHandoffResumePrompt,
      })
    );
    logEvent(`adaptive patience raised after interruption (${interruptCount})`);
  }

  function clearRecoveryMode() {
    if (!ws || ws.readyState !== WebSocket.OPEN || !recoveryModeArmed) return;
    recoveryModeArmed = false;
    interruptCount = Math.max(0, interruptCount - 1);
    ws.send(
      JSON.stringify({
        type: "config",
        reason: "recovery_complete",
        interrupt_count: interruptCount,
        interruption_recovery: false,
        triage_context: latestTriageContext,
        ledger_context: currentLedgerContextForWire(),
        dispatch_context: currentDispatchContextForWire(),
        human_takeover_active: humanTakeoverEngaged,
        handoff_recovery_prompt: pendingHandoffResumePrompt,
      })
    );
  }

  function sendTriageConfig(reason = "triage_update") {
    const hasControlUpdate = humanTakeoverEngaged || Boolean(pendingHandoffResumePrompt);
    if (!ws || ws.readyState !== WebSocket.OPEN || (!latestTriageContext && !latestLedgerContext && !latestDispatchContext && !hasControlUpdate)) return;
    const dispatchContext = currentDispatchContextForWire();
    ws.send(
      JSON.stringify({
        type: "config",
        reason,
        interrupt_count: interruptCount,
        interruption_recovery: recoveryModeArmed,
        triage_context: latestTriageContext,
        ledger_context: currentLedgerContextForWire(),
        dispatch_context: dispatchContext,
        human_takeover_active: humanTakeoverEngaged,
        handoff_recovery_prompt: pendingHandoffResumePrompt,
      })
    );
    if (latestDispatchContext?.announcement_line) {
      latestDispatchContext = { ...latestDispatchContext, announcement_line: null };
    }
  }

  function scheduleTriageSync() {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (triageSyncTimeout) {
      clearTimeout(triageSyncTimeout);
    }
    triageSyncTimeout = setTimeout(() => {
      triageSyncTimeout = null;
      syncSessionReport("live").catch(() => {});
    }, 150);
  }

  function initMap() {
    if (!window.L || map) return;
    map = window.L.map("map", {
      zoomControl: false,
      attributionControl: true,
    }).setView([52.52, 13.405], 5);

    window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);

    window.L.control
      .zoom({
        position: "bottomright",
      })
      .addTo(map);
    invalidateMapSizeSoon();
  }

  function invalidateMapSizeSoon() {
    if (!map) return;
    window.requestAnimationFrame(() => {
      window.setTimeout(() => {
        if (map) {
          map.invalidateSize(false);
        }
      }, 80);
    });
  }

  function clearMapState() {
    if (mapMarker && map) {
      map.removeLayer(mapMarker);
      mapMarker = null;
    }
    lastMapAnimationKey = null;
    if (map) {
      map.setView([52.52, 13.405], 5);
    }
    mapStatusEl.textContent = "Waiting for a geocoded location.";
  }

  function updateMap(state) {
    initMap();
    const { lat, lon, location, mapSource, mapConfidence, mapCandidates, locationNeedsConfirmation, dispatchServices } = state;
    if (lat == null || lon == null || !map) {
      const candidateText =
        locationNeedsConfirmation
          ? `Location candidate needs caller confirmation: ${location}.`
          : mapCandidates && mapCandidates.length
          ? `No exact pin yet. Best text match: ${mapCandidates[0].display_name || location}.`
          : location && location !== "Pending"
            ? `No exact pin yet. Current location text: ${location}.`
            : "Waiting for a geocoded location.";
      mapStatusEl.textContent = candidateText;
      if (map && location && location !== "Pending") {
        map.setView([52.52, 13.405], 11);
        invalidateMapSizeSoon();
      }
      return;
    }

    const coordinates = [lat, lon];
    const serviceStateKey = Object.entries(dispatchServices || {})
      .map(([name, value]) => `${name}:${value.status}`)
      .join("|");
    const animationKey = `${lat}:${lon}:${serviceStateKey}`;
    if (!mapMarker) {
      mapMarker = window.L.marker(coordinates).addTo(map);
    } else {
      mapMarker.setLatLng(coordinates);
    }
    mapMarker.bindPopup(escapeHtml(location)).openPopup();
    if (lastMapAnimationKey !== animationKey) {
      lastMapAnimationKey = animationKey;
      map.flyTo(coordinates, 15, { animate: true, duration: 0.85 });
    } else {
      map.setView(coordinates, 14);
    }
    invalidateMapSizeSoon();
    mapStatusEl.textContent = `${location} · ${mapSource || "map"} · ${mapConfidence || "pending"} confidence`;
  }

  function float32ToPcm16Buffer(float32Samples) {
    const int16 = new Int16Array(float32Samples.length);
    for (let i = 0; i < float32Samples.length; i += 1) {
      const sample = Math.max(-1, Math.min(1, float32Samples[i]));
      int16[i] = sample < 0 ? sample * 32768 : sample * 32767;
    }
    return int16.buffer;
  }

  function resampleToTargetRate(inputSamples, sourceRate, targetRate) {
    if (!inputSamples || !inputSamples.length) {
      return new Float32Array(0);
    }
    if (!sourceRate || !targetRate || sourceRate === targetRate) {
      return new Float32Array(inputSamples);
    }
    if (sourceRate === targetRate * 2) {
      const out = new Float32Array(Math.floor(inputSamples.length / 2));
      let outIdx = 0;
      for (let i = 0; i + 1 < inputSamples.length; i += 2) {
        out[outIdx] = (inputSamples[i] + inputSamples[i + 1]) * 0.5;
        outIdx += 1;
      }
      return out;
    }

    const ratio = sourceRate / targetRate;
    const outputLength = Math.max(1, Math.floor(inputSamples.length / ratio));
    const output = new Float32Array(outputLength);
    for (let i = 0; i < outputLength; i += 1) {
      const srcPos = i * ratio;
      const leftIdx = Math.floor(srcPos);
      const rightIdx = Math.min(leftIdx + 1, inputSamples.length - 1);
      const frac = srcPos - leftIdx;
      const left = inputSamples[leftIdx] || 0;
      const right = inputSamples[rightIdx] || left;
      output[i] = left + (right - left) * frac;
    }
    return output;
  }

  function flushPcmPending(forcePad = false) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const chunkSamples = currentAudioConfig.chunk_samples || 1920;
    while (pcmCapturePending.length >= chunkSamples) {
      const chunk = new Float32Array(pcmCapturePending.slice(0, chunkSamples));
      pcmCapturePending = pcmCapturePending.slice(chunkSamples);
      ws.send(float32ToPcm16Buffer(chunk));
    }
    if (forcePad && pcmCapturePending.length) {
      const padded = new Float32Array(chunkSamples);
      padded.set(pcmCapturePending.slice(0, chunkSamples));
      pcmCapturePending = [];
      ws.send(float32ToPcm16Buffer(padded));
    }
  }

  function stopPcmCapture() {
    pcmCapturePending = [];
    if (pcmCaptureNode) {
      pcmCaptureNode.disconnect();
      pcmCaptureNode.onaudioprocess = null;
      pcmCaptureNode = null;
    }
    if (pcmCaptureSource) {
      pcmCaptureSource.disconnect();
      pcmCaptureSource = null;
    }
    if (pcmCaptureSink) {
      pcmCaptureSink.disconnect();
      pcmCaptureSink = null;
    }
  }

  function startPcmCapture(playerInstance, audioConfig) {
    stopPcmCapture();
    if (!audioConfig.pcm_input) return;
    const audioProcessor = playerInstance?.audioProcessor;
    const audioContext = audioProcessor?.audioContext;
    const mediaStream = audioProcessor?.mediaStream;
    if (!audioContext || !mediaStream) {
      logEvent("pcm microphone uplink unavailable", "error");
      return;
    }

    pcmCaptureSource = audioContext.createMediaStreamSource(mediaStream);
    pcmCaptureNode = audioContext.createScriptProcessor(4096, 1, 1);
    pcmCaptureSink = audioContext.createGain();
    pcmCaptureSink.gain.value = 0;

    pcmCaptureNode.onaudioprocess = (event) => {
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      const input = event.inputBuffer.getChannelData(0);
      if (!input || !input.length) return;
      const resampled = resampleToTargetRate(
        input,
        audioContext.sampleRate,
        audioConfig.sample_rate || audioContext.sampleRate
      );
      for (let i = 0; i < resampled.length; i += 1) {
        pcmCapturePending.push(resampled[i]);
      }
      flushPcmPending(false);
    };

    pcmCaptureSource.connect(pcmCaptureNode);
    pcmCaptureNode.connect(pcmCaptureSink);
    pcmCaptureSink.connect(audioContext.destination);
    logEvent(
      `pcm microphone uplink enabled (${audioContext.sampleRate} Hz -> ${audioConfig.sample_rate || audioContext.sampleRate} Hz)`
    );
  }

  async function createPlayer(audioConfig) {
    currentAudioConfig = audioConfig;
    const syncedPlayer = new window.SyncedAudioPlayer({
      basePath: "/static/js",
      pcmOutput: Boolean(audioConfig.pcm),
      onEncodedAudio: (audioData) => {
        if (!audioConfig.pcm_input && ws && ws.readyState === WebSocket.OPEN) {
          ws.send(audioData);
        }
      },
      onMetrics: (metrics) => {
        const bufferMs = Math.round(metrics.bufferMs || 0);
        maxBufferMs = Math.max(maxBufferMs, bufferMs);
        bufferMetricEl.textContent = `${bufferMs} ms`;
      },
      onText: ({ text, isUser }) => {
        logTranscript(text, isUser);
      },
      onEvent: (eventName) => {
        logEvent(eventName);
        if (["push_to_llm", "llm_started", "first_word", "first_tts_audio"].includes(eventName)) {
          assistantTurnActive = true;
        }
        if (eventName === "previous_llm_gen") {
          raiseAdaptivePatience("caller_interrupt");
        }
      },
      onError: (error) => {
        logEvent(error.message || String(error), "error");
        setStatus("Error", "error");
      },
      onEndOfTurn: () => {
        assistantTurnActive = false;
        finalizePendingAgent("turn_end");
        logEvent("assistant turn finished");
        clearRecoveryMode();
        if (pendingTriageUpdate) {
          const queuedUpdate = pendingTriageUpdate;
          pendingTriageUpdate = null;
          pushTriageContext(queuedUpdate);
        }
        if (pendingLedgerUpdate) {
          const queuedUpdate = pendingLedgerUpdate;
          pendingLedgerUpdate = null;
          pushLedgerContext(queuedUpdate);
        }
        if (pendingDispatchUpdate) {
          const queuedDispatch = pendingDispatchUpdate;
          pendingDispatchUpdate = null;
          pushDispatchContext(queuedDispatch);
        }
      },
    });
    await syncedPlayer.start();
    if (audioConfig.pcm_input) {
      startPcmCapture(syncedPlayer, audioConfig);
    }
    return syncedPlayer;
  }

  function buildSessionReport(status) {
    return {
      session_id: sessionId,
      status,
      triage_mode: getSelectedDispatchMode(),
      started_at: sessionStartedAt,
      ended_at: new Date().toISOString(),
      transcripts: {
        user: userTranscripts,
        agent: agentTranscripts,
      },
      events: eventEntries,
      metrics: {
        max_buffer_ms: maxBufferMs,
      },
      page: {
        href: window.location.href,
      },
    };
  }

  function pushTriageContext(update) {
    if (!update || !update.prompt_context) return;
    latestTriageContext = update.prompt_context;
    const version = Number(update.version || update.prompt_context.version || 0);
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (!version || version <= lastTriageVersionSent) return;
    if (assistantTurnActive) {
      pendingTriageUpdate = update;
      return;
    }
    lastTriageVersionSent = version;
    sendTriageConfig("triage_update");
    logEvent(`triage context updated (${version})`);
  }

  function pushLedgerContext(update) {
    if (!update || !update.prompt_context) return;
    latestLedgerContext = update.prompt_context;
    const version = Number(update.version || update.prompt_context.version || 0);
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (!version || version <= lastLedgerVersionSent) return;
    if (assistantTurnActive) {
      pendingLedgerUpdate = update;
      return;
    }
    lastLedgerVersionSent = version;
    sendTriageConfig("ledger_update");
    logEvent(`shared ledger updated (${version})`);
  }

  function pushDispatchContext(update) {
    if (!update || !update.prompt_context) return;
    latestDispatchContext = update.prompt_context;
    const version = Number(update.version || update.prompt_context.version || 0);
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (!version || version <= lastDispatchVersionSent) return;
    if (assistantTurnActive) {
      pendingDispatchUpdate = update;
      return;
    }
    lastDispatchVersionSent = version;
    sendTriageConfig("dispatch_update");
    logEvent(`dispatch operations updated (${version})`);
  }

  async function syncSessionReport(status = "live") {
    if (!sessionId) return;
    const result = await fetch("/api/session-report", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(buildSessionReport(status)),
      keepalive: true,
    })
      .then((res) => res.json())
      .catch(() => null);
    if (result?.triage_update?.prompt_context) {
      pushTriageContext(result.triage_update);
    }
    if (result?.ledger_update?.prompt_context) {
      pushLedgerContext(result.ledger_update);
    }
    if (result?.dispatch_update?.prompt_context) {
      pushDispatchContext(result.dispatch_update);
    }
    if (result?.stt_rescue_event) {
      const rescueIndex = Number(result.stt_rescue_event.user_index ?? -1);
      if (rescueIndex > lastRescueIndexSeen) {
        lastRescueIndexSeen = rescueIndex;
        logEvent(
          `stt rescue ${result.stt_rescue_event.selected_provider}: ${result.stt_rescue_event.corrected_transcript}`
        );
      }
    }
    return result;
  }

  function flushSessionReport(status) {
    if (!sessionId || reportSent) return;
    reportSent = true;
    const payload = JSON.stringify(buildSessionReport(status));
    const blob = new Blob([payload], { type: "application/json" });
    if (navigator.sendBeacon) {
      navigator.sendBeacon("/api/session-report", blob);
      return;
    }
    fetch("/api/session-report", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: payload,
      keepalive: true,
    }).catch(() => {});
  }

  function setMemoryPanel(session) {
    if (!session) {
      memoryPanelEl.innerHTML = `
        <article class="entry event">
          <div class="body">Start a call to populate the stored session state.</div>
        </article>
      `;
      return;
    }
    const server = session.server || {};
    const client = session.client || {};
    const turns = client.transcripts || {};
    const userTurns = (turns.user || []).length;
    const agentTurns = (turns.agent || []).length;
    memoryPanelEl.innerHTML = `
      <div class="kv-list">
        <div class="kv-row"><span>Session</span><strong>${escapeHtml(session.session_id || "n/a")}</strong></div>
        <div class="kv-row"><span>Server</span><strong>${escapeHtml(server.status || "waiting")}</strong></div>
        <div class="kv-row"><span>Client</span><strong>${escapeHtml(client.status || "live")}</strong></div>
        <div class="kv-row"><span>Turns</span><strong>${userTurns} caller / ${agentTurns} dispatcher</strong></div>
        <div class="kv-row"><span>Updated</span><strong>${escapeHtml(session.updated_at || "n/a")}</strong></div>
      </div>
    `;
  }

  function computeSeverity(session, state) {
    const triageMeta = session.triage_meta || {};
    const merged = session.merged_triage_state || {};
    const handoff = session.handoff_packet || null;
    const callerText = latestTranscriptText(session?.client?.transcripts?.user, 5).toLowerCase();
    const summaryText = String(state.ticketCall?.result?.caller_summary || "").toLowerCase();
    const combinedText = `${callerText} ${summaryText}`;
    const drivers = [];

    let score =
      {
        CRITICAL: 86,
        HIGH: 66,
        MEDIUM: 42,
        LOW: 18,
      }[String(state.priority || merged.priority || "").toUpperCase()] || 8;

    const issueType = String(state.issueType || merged.issue_type || "").toUpperCase();
    if (issueType === "FIRE") {
      score += 8;
      drivers.push("fire risk");
    } else if (issueType === "POLICE" || issueType === "HAZMAT") {
      score += 10;
      drivers.push("active danger");
    } else if (issueType === "MEDICAL") {
      score += 7;
      drivers.push("medical risk");
    } else if (issueType === "TRAFFIC") {
      score += 5;
      drivers.push("traffic injury");
    }

    const keywordDrivers = [
      ["smoke", 12, "smoke reported"],
      ["fire", 14, "fire reported"],
      ["trapped", 12, "people trapped"],
      ["bleeding", 12, "bleeding risk"],
      ["not breathing", 22, "breathing failure"],
      ["breathing", 8, "breathing uncertainty"],
      ["shot", 20, "violence reported"],
      ["shooting", 20, "violence reported"],
      ["child", 14, "child involved"],
      ["daughter", 14, "child involved"],
      ["son", 14, "child involved"],
      ["asthma", 12, "breathing vulnerability"],
      ["water", 18, "water hazard"],
      ["drowning", 24, "drowning risk"],
    ];

    for (const [term, weight, label] of keywordDrivers) {
      if (combinedText.includes(term)) {
        score += weight;
        if (!drivers.includes(label)) drivers.push(label);
      }
    }

    if (handoff || merged.escalate_to_human || triageMeta.autonomy_allowed === false) {
      score = Math.max(score, 72);
      if (!drivers.includes("human handoff advised")) drivers.push("human handoff advised");
    }

    const missing = triageMeta.missing_or_unknown_fields || [];
    if (missing.length && score >= 60) {
      score += Math.min(10, missing.length * 2);
      drivers.push(`${missing.length} unresolved fields`);
    }

    if (!state.hasPin && score >= 50) {
      score += 8;
      drivers.push("location not pinned");
    }

    if (state.hasPin) {
      drivers.push("location pinned");
    }

    score = Math.max(0, Math.min(100, Math.round(score)));
    const band = severityBand(score);
    const headline = humanTakeoverEngaged ? "Human Takeover Engaged" : severityHeadline(score);
    const subtext = humanTakeoverEngaged
      ? "Operator has manually taken the call surface. Backend automation remains visible for reference."
      : drivers.slice(0, 3).join(" · ") || "Waiting for stable call context.";

    return {
      score,
      band,
      headline,
      subtext,
      drivers,
    };
  }

  function isLowSignalSummary(text) {
    const normalized = String(text || "").trim();
    if (!normalized) return true;
    const compact = normalized.toLowerCase();
    const confirmations = (compact.match(/\b(?:yes|no|maybe|okay|ok|correct|sorry)\b/g) || []).length;
    const uncertainty = (compact.match(/\b(?:i don't know|dont know|not sure)\b/g) || []).length;
    const sentenceCount = normalized
      .split(/[.!?]+/)
      .map((part) => part.trim())
      .filter(Boolean).length;
    if (/(?:\byes\b[,. ]*){2,}|(?:\bno\b[,. ]*){2,}/i.test(compact)) return true;
    if (confirmations + uncertainty >= 4 && normalized.length >= 60) return true;
    if (sentenceCount >= 5 && confirmations >= 2) return true;
    return false;
  }

  function selectStickySummary(handoffBrief, ticket, latestCaller) {
    const candidates = [
      handoffBrief.one_line,
      handoffBrief.caller_summary,
      ticket.caller_summary,
      latestCaller,
    ]
      .map((item) => String(item || "").trim())
      .filter(Boolean);

    for (const candidate of candidates) {
      if (!isLowSignalSummary(candidate)) {
        stickySummaryText = candidate;
        return candidate;
      }
    }
    return stickySummaryText || "Processing...";
  }

  function buildOperatorBrief(session, state, severity) {
    const triageMeta = session.triage_meta || {};
    const merged = session.merged_triage_state || {};
    const handoff = session.handoff_packet || null;
    const latestCaller = latestTranscriptText(session?.client?.transcripts?.user, 4);
    const ticket = state.ticketCall?.result || {};
    const handoffBrief = state.handoffBriefCall?.result || {};
    const summary = selectStickySummary(handoffBrief, ticket, latestCaller);
    const confirmed = [];
    if (state.location && state.location !== "Pending") {
      confirmed.push(`Location: ${state.location}`);
    }
    if (state.hasPin) {
      confirmed.push(`Pinned coordinates: ${state.lat}, ${state.lon}`);
    }
    if (state.issueType && state.issueType !== "Pending") {
      confirmed.push(`Issue: ${titleCase(state.issueType)}`);
    }
    if (state.priority && state.priority !== "Pending") {
      confirmed.push(`Priority: ${state.priority}`);
    }
    if (state.humanMonitoring && state.monitorName) {
      confirmed.push(`Human monitoring: ${state.monitorName} is watching this call`);
    }
    const serviceItems = Object.values(state.dispatchServices || {}).filter((item) => item && item.needed);
    if (serviceItems.length) {
      confirmed.push(
        "Services: " +
          serviceItems
            .map((item) => `${item.label} ${String(item.status_label || item.status || "").toLowerCase()} (${item.eta_text})`)
            .join(" · ")
      );
    }

    if (!confirmed.length && Array.isArray(handoffBrief.confirmed_facts)) {
      confirmed.push(...handoffBrief.confirmed_facts);
    }

    const unknowns =
      (triageMeta.missing_or_unknown_fields || []).length
        ? (triageMeta.missing_or_unknown_fields || []).map(humanizeField)
        : Array.isArray(handoffBrief.unknowns)
          ? handoffBrief.unknowns
          : [];
    let nextMove = "Human can take over with the current packet and continue live questioning.";
    if (humanTakeoverEngaged) {
      nextMove = "Human operator is on the line. Press hand back when you want the agent to resume with a status check.";
    } else
    if (!state.hasPin) {
      nextMove = "Get one landmark or road sign. If the place name sounds unstable, ask the caller to spell it.";
    } else if (state.humanMonitoring && state.monitorName) {
      nextMove = `${state.monitorName} is watching the call while services continue moving. Keep the caller steady and do not stack questions.`;
    } else if (unknowns.includes("Breathing status")) {
      nextMove = "Confirm breathing with a yes/no question before adding more instructions.";
    } else if (unknowns.includes("Victim count")) {
      nextMove = "Confirm how many people are involved before widening the response.";
    } else if (unknowns.includes("Caller safety")) {
      nextMove = "Confirm whether the caller is currently safe where they are standing.";
    } else if (severity.score >= 86) {
      nextMove = "Keep the caller on the line, keep instructions short, and prepare immediate human takeover.";
    } else if (handoffBrief.next_question_goal && handoffBrief.next_question_goal !== "hold steady") {
      nextMove = handoffBrief.next_question_goal;
    }

    return {
      summary,
      confirmed,
      unknowns,
      nextMove,
      escalationReason: merged.escalation_reason || handoff?.escalation_reason || "None yet",
      recommendedMode:
        severity.score >= 86
          ? "Holding pattern"
          : severity.score >= 61
            ? "Pre-arrival priority"
            : severity.score >= 31
              ? "Single clear question"
              : "Normal triage",
    };
  }

  function renderOperatorDesk(session, state) {
    const severity = computeSeverity(session, state);
    const brief = buildOperatorBrief(session, state, severity);
    const severityClass = `severity-${severity.band}`;

    severityHeroEl.className = `severity-hero ${severityClass}`;
    severityScoreEl.textContent = `${severity.score} / 100`;
    severitySubtextEl.textContent = severity.subtext;
    const buttonLabel = humanTakeoverEngaged
      ? "Hand Back To Agent"
      : severity.score >= 86
        ? "Take Over Now"
        : severity.score >= 61
          ? "Request Human"
          : severity.score >= 31
            ? "Human Review"
            : "Human Standby";
    takeoverBtn.textContent = buttonLabel;
    takeoverBtn.className = `button takeover-button ${severityClass}${humanTakeoverEngaged ? " engaged" : ""}`;
    takeoverBtn.disabled = !sessionId;

    operatorReportEl.innerHTML = `
      <div class="report-grid">
        <article class="report-card">
          <div class="section-label">Operator Status</div>
          <strong>${escapeHtml(severity.headline)}</strong>
          <p>${escapeHtml(brief.nextMove)}</p>
          <p><span class="chip-label">Mode</span> ${escapeHtml(brief.recommendedMode)}</p>
          <p><span class="chip-label">Escalation</span> ${escapeHtml(brief.escalationReason)}</p>
        </article>
        <article class="report-card">
          <div class="section-label">Live Summary</div>
          <strong>${escapeHtml(brief.summary)}</strong>
        </article>
        <article class="report-card">
          <div class="section-label">Confirmed Facts</div>
          ${
            brief.confirmed.length
              ? `<ul>${brief.confirmed.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
              : `<p>No confirmed facts yet.</p>`
          }
        </article>
        <article class="report-card">
          <div class="section-label">Still Unknown</div>
          ${
            brief.unknowns.length
              ? `<ul>${brief.unknowns.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
              : `<p>No major gaps right now.</p>`
          }
        </article>
      </div>
    `;

    dispatchMetricEl.textContent = humanTakeoverEngaged ? "Human takeover engaged" : severity.headline;
  }

  function renderServicePanel(state) {
    const services = Object.values(state.dispatchServices || {}).filter((item) => item && item.needed);
    if (!services.length) {
      servicePanelEl.innerHTML = `
        <article class="service-card service-card-pending">
          <div class="service-top">
            <strong>Services</strong>
            <span class="service-state">Pending</span>
          </div>
          <p>No service movement yet.</p>
          <small>The server will identify police, ambulance, or fire once the hard facts are stable enough.</small>
        </article>
      `;
      return;
    }
    servicePanelEl.innerHTML = services
      .map(
        (service) => `
          <article class="service-card service-card-${escapeHtml(String(service.status || "pending").toLowerCase())}">
            <div class="service-top">
              <strong>${escapeHtml(service.label || "Service")}</strong>
              <span class="service-state">${escapeHtml(service.status_label || titleCase(service.status || "pending"))}</span>
            </div>
            <p>${escapeHtml(service.detail || "No update yet.")}</p>
            <small>${escapeHtml(`${service.unit_label || "Nearest unit"} · ${service.eta_text || "Pending"}`)}</small>
            ${
              service.base_name || service.base_address || service.distance_km != null
                ? `<small>${escapeHtml(
                    [
                      service.base_name,
                      service.base_address,
                      service.distance_km != null ? `${service.distance_km} km` : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")
                  )}</small>`
                : ""
            }
          </article>
        `
      )
      .join("");
  }

  function summarizeToolCall(toolCall) {
    const { name, args = {}, result = {}, error } = toolCall;
    if (error) return error;

    if (name === "resolve_location_note") {
      return `${result.location_status || "pending"} · ${result.normalized_note || result.sub_location || args.location_note || "pending"}`;
    }
    if (name === "nearby_context") {
      return `${result.resolved ? "context ready" : "pending"} · ${result.summary || result.normalized_address || args.address_text || "pending"}`;
    }
    if (name === "checklist_by_incident") {
      return `${result.next_question_goal || "holding"} · ${(result.missing_fields || []).length} gaps`;
    }
    if (name === "build_handoff_brief") {
      return `${result.status || "draft"} · ${result.one_line || "brief pending"}`;
    }
    if (name === "plan_response_services") {
      return `${(result.needed_services || []).join(", ") || "no services"} · ${result.priority || "pending"}`;
    }
    if (name === "lookup_response_bases") {
      return `${result.resolved ? "bases found" : "no bases"} · ${result.summary || "pending"}`;
    }
    if (name === "simulate_dispatch_services") {
      return `${result.summary || "no service movement"}${result.announcement_line ? ` · ${result.announcement_line}` : ""}`;
    }
    if (name === "assign_dispatch_priority") {
      return `${result.priority || "pending"} · ${result.dispatch_lane || "no lane"}`;
    }
    if (name === "create_incident_ticket") {
      return `${result.status || "created"} · ${result.priority || args.priority || "pending"} · ${result.address || args.address || "location pending"}`;
    }
    if (name === "validate_address") {
      return `${result.candidate_only ? "candidate" : result.valid ? "valid" : "invalid"} · ${result.normalized_address || args.address_text || "pending"}`;
    }
    if (name === "lookup_address") {
      return `${result.candidate_only ? "candidate" : result.found ? "matched" : "unmatched"} · ${result.normalized_address || args.address_text || "pending"}`;
    }
    return "completed";
  }

  function toolStageDefinitions() {
    return [
      {
        name: "resolve_location_note",
        title: "Location Note",
        eyebrow: "Step 1",
        formatter(toolCall) {
          const result = toolCall?.result || {};
          if (!toolCall) return { status: "pending", summary: "Landmarks, entrances, and floor notes will land here.", meta: "Best-effort clue capture." };
          if (toolCall.error) return { status: "error", summary: toolCall.error, meta: "Location note resolution failed." };
          return {
            status: result.usable_for_dispatch ? "complete" : "watch",
            summary: result.normalized_note || result.sub_location || toolCall.args?.location_note || "No note captured yet.",
            meta: `${titleCase(result.note_type || "none")} · ${titleCase(result.location_status || "missing")}`,
          };
        },
      },
      {
        name: "checklist_by_incident",
        title: "Question Checklist",
        eyebrow: "Step 2",
        formatter(toolCall) {
          const result = toolCall?.result || {};
          if (!toolCall) return { status: "pending", summary: "Gradbot will queue the next hard fact here.", meta: "Highest-priority missing fact." };
          if (toolCall.error) return { status: "error", summary: toolCall.error, meta: "Checklist generation failed." };
          return {
            status: (result.missing_fields || []).length ? "watch" : "complete",
            summary: result.next_question_goal || "Hold steady",
            meta: `${(result.missing_fields || []).length} gaps · ${result.location_search_allowed ? "search allowed" : "search guarded"}`,
          };
        },
      },
      {
        names: ["validate_address", "lookup_address"],
        title: "Location Check",
        eyebrow: "Step 3",
        formatter(toolCall) {
          const result = toolCall?.result || {};
          if (!toolCall) return { status: "pending", summary: "A searchable road, junction, or named place will be checked here.", meta: "Pin and readback." };
          if (toolCall.error) return { status: "error", summary: toolCall.error, meta: "Location check failed." };
          if (result.candidate_only) {
            return {
              status: "watch",
              summary: result.normalized_address || toolCall.args?.address_text || "Candidate location pending confirmation.",
              meta: "Needs caller confirmation",
            };
          }
          const resolved = Boolean(result.valid ?? result.found ?? result.geocoded);
          return {
            status: resolved ? "complete" : "watch",
            summary: result.normalized_address || toolCall.args?.address_text || "No stable location yet.",
            meta:
              toolCall.name === "validate_address"
                ? `${result.valid ? "valid" : "guarded"} · ${titleCase(result.reason || result.source || "pending")}`
                : `${result.found ? "matched" : "guarded"} · ${titleCase(result.reason || result.source || "pending")}`,
          };
        },
      },
      {
        name: "nearby_context",
        title: "Nearby Context",
        eyebrow: "Step 4",
        formatter(toolCall) {
          const result = toolCall?.result || {};
          if (!toolCall) return { status: "pending", summary: "Context appears once a stable place or address lands.", meta: "Roads, landmarks, and area hints." };
          if (toolCall.error) return { status: "error", summary: toolCall.error, meta: "Nearby context failed." };
          return {
            status: result.resolved ? "complete" : "watch",
            summary: result.summary || result.normalized_address || "No context yet.",
            meta: result.resolved ? `${(result.major_roads || []).length} roads · ${(result.landmarks || []).length} landmarks` : titleCase(result.reason || "pending"),
          };
        },
      },
      {
        name: "build_handoff_brief",
        title: "Handoff Brief",
        eyebrow: "Step 5",
        formatter(toolCall) {
          const result = toolCall?.result || {};
          if (!toolCall) return { status: "pending", summary: "A compact operator brief will appear when facts are stable.", meta: "Ready for operations." };
          if (toolCall.error) return { status: "error", summary: toolCall.error, meta: "Brief build failed." };
          return {
            status: result.status === "ready" ? "complete" : result.status ? "watch" : "pending",
            summary: result.one_line || "Facts still being gathered",
            meta: titleCase(result.status || "gathering"),
          };
        },
      },
      {
        name: "lookup_response_bases",
        title: "Nearest Bases",
        eyebrow: "Step 6",
        formatter(toolCall) {
          const result = toolCall?.result || {};
          if (!toolCall) return { status: "pending", summary: "Nearest hospital, police, and fire bases will appear here after a pin lands.", meta: "Grounded dispatch references." };
          if (toolCall.error) return { status: "error", summary: toolCall.error, meta: "Nearest-base lookup failed." };
          return {
            status: result.resolved ? "complete" : "watch",
            summary: result.summary || "No nearby bases found.",
            meta: titleCase(result.source || "pending"),
          };
        },
      },
      {
        name: "plan_response_services",
        title: "Service Plan",
        eyebrow: "Step 7",
        formatter(toolCall) {
          const result = toolCall?.result || {};
          if (!toolCall) return { status: "pending", summary: "Services will be selected once the issue is grounded.", meta: "Police, ambulance, fire." };
          if (toolCall.error) return { status: "error", summary: toolCall.error, meta: "Service plan failed." };
          return {
            status: (result.needed_services || []).length ? "complete" : "watch",
            summary: (result.needed_services || []).map((item) => titleCase(item)).join(" · ") || "No services selected",
            meta: `${result.priority || "Pending"} · ${result.human_monitoring ? "Alex monitoring" : "autonomous"}`,
          };
        },
      },
      {
        name: "simulate_dispatch_services",
        title: "Dispatch Movement",
        eyebrow: "Step 8",
        formatter(toolCall) {
          const result = toolCall?.result || {};
          if (!toolCall) return { status: "pending", summary: "Nearest-unit lookup and dispatch theatrics appear here.", meta: "Locating, assigned, dispatched." };
          if (toolCall.error) return { status: "error", summary: toolCall.error, meta: "Dispatch simulation failed." };
          return {
            status: result.dispatchable ? "complete" : "watch",
            summary: result.summary || "No service movement yet.",
            meta: result.announcement_line || (result.human_monitoring ? "Human monitor active" : "Waiting for dispatchable facts"),
          };
        },
      },
    ];
  }

  function renderToolChain(session) {
    const toolCalls = session.tool_calls || [];
    const stages = toolStageDefinitions().map((stage) => {
      const toolCall = stage.names ? latestToolCallAny(toolCalls, stage.names) : latestToolCall(toolCalls, stage.name);
      return { ...stage, toolCall, view: stage.formatter(toolCall) };
    });
    const activeCount = stages.filter((stage) => stage.toolCall && !stage.toolCall.error).length;

    toolChainEl.innerHTML = `
      <div class="tool-chain-shell">
        <div class="tool-chain-head">
          <div>
            <div class="section-label">Gradbot At Work</div>
            <strong>Deterministic Assist Chain</strong>
          </div>
          <span class="tool-chain-badge">${escapeHtml(String(activeCount))} / ${escapeHtml(String(stages.length))} active</span>
        </div>
        <div class="tool-stage-stack">
          ${stages
            .map(
              (stage) => `
                <article class="tool-stage tool-stage-${escapeHtml(stage.view.status)}">
                  <div class="tool-stage-index">${escapeHtml(stage.eyebrow)}</div>
                  <div class="tool-stage-copy">
                    <div class="tool-stage-top">
                      <strong>${escapeHtml(stage.title)}</strong>
                      <span class="tool-stage-state">${escapeHtml(titleCase(stage.view.status))}</span>
                    </div>
                    <p>${escapeHtml(stage.view.summary)}</p>
                    <small>${escapeHtml(stage.view.meta)}</small>
                  </div>
                </article>
              `
            )
            .join("")}
        </div>
      </div>
    `;
  }

  function renderTriagePanel(session) {
    const latestTurn = [...(session.triage_turns || [])].reverse()[0];
    const merged = session.merged_triage_state || {};
    const triageMeta = session.triage_meta || {};
    const serverMode = normalizeDispatchMode(session.server?.live_dispatch_mode || session.server?.triage_engine);
    const overrides = session.rule_overrides || [];
    const handoff = session.handoff_packet;
    const rescueEvents = session.stt_rescue_events || [];
    const latestRescue = rescueEvents.length ? rescueEvents[rescueEvents.length - 1] : null;
    const sttMeta = session.stt_rescue_meta || {};
    if (serverMode === "llm_only") {
      triagePanelEl.innerHTML = `
        <div class="kv-list">
          <div class="kv-row"><span>Mode</span><strong>${escapeHtml(dispatchModeLabel(serverMode))}</strong></div>
          <div class="kv-row"><span>STT Active</span><strong>${escapeHtml(sttMeta.active_provider || "gradium")}</strong></div>
          <div class="kv-row"><span>STT Compare Mode</span><strong>${escapeHtml((sttMeta.continuous_compare ?? false) ? "continuous" : "rescue-only")}</strong></div>
          <div class="kv-row"><span>Shadow Active</span><strong>${escapeHtml(String(sttMeta.shadow_active ?? false))}</strong></div>
          <div class="kv-row"><span>Shadow Elapsed</span><strong>${escapeHtml(String(sttMeta.shadow_elapsed_s ?? 0))} s</strong></div>
        </div>
        <div class="ticket-summary">
          <div class="section-label">LLM Only Path</div>
          <p>Live rescue compare stays on, but structured triage inference is bypassed so you can judge the raw Gradium voice path.</p>
        </div>
        <div class="ticket-summary">
          <div class="section-label">STT Rescue</div>
          ${
            latestRescue
              ? `<pre>${escapeHtml(JSON.stringify(latestRescue, null, 2))}</pre>`
              : `<p>No rescue events yet.</p>`
          }
        </div>
      `;
      return;
    }
    const sharedLedger = session.shared_ledger || null;
    if (serverMode === "slm" && sharedLedger) {
      const hardFacts = sharedLedger.hard_facts || {};
      const softState = sharedLedger.soft_state || {};
      const priority = sharedLedger.priority || {};
      const locationGate = sharedLedger.location_gate || {};
      const provenance = sharedLedger.provenance || {};
      const confirmedFacts = [];
      if ((hardFacts.issue_cues || []).length) {
        confirmedFacts.push(`Issue cues: ${(hardFacts.issue_cues || []).map(titleCase).join(", ")}`);
      }
      if (hardFacts.location_candidate || locationGate.candidate_text) {
        confirmedFacts.push(`Location candidate: ${hardFacts.location_candidate || locationGate.candidate_text}`);
      }
      if (hardFacts.sub_location) {
        confirmedFacts.push(`Sub-location: ${hardFacts.sub_location}`);
      }
      if (hardFacts.victim_count_confirmed !== "unknown") {
        confirmedFacts.push(`Confirmed people count: ${hardFacts.victim_count_confirmed}`);
      }
      ["child_present", "bleeding_status", "breathing_status", "consciousness_status", "trapped_status"].forEach((field) => {
        if (hardFacts[field] && hardFacts[field] !== "unknown") {
          confirmedFacts.push(`${humanizeField(field)}: ${hardFacts[field]}`);
        }
      });
      const softGuesses = [];
      if (softState.people_count_best_guess != null) {
        softGuesses.push(`People count estimate: ${softState.people_count_best_guess}`);
      }
      if (softState.caller_role && softState.caller_role !== "unknown") {
        softGuesses.push(`Caller role: ${softState.caller_role}`);
      }
      (softState.notes || []).forEach((note) => softGuesses.push(note));
      triagePanelEl.innerHTML = `
        <div class="kv-list">
          <div class="kv-row"><span>Mode</span><strong>${escapeHtml(dispatchModeLabel(serverMode))}</strong></div>
          <div class="kv-row"><span>SLM Status</span><strong>${escapeHtml(provenance.slm_job_state || "idle")}</strong></div>
          <div class="kv-row"><span>Ledger Version</span><strong>${escapeHtml(String(sharedLedger.version || 0))}</strong></div>
          <div class="kv-row"><span>Last SLM Run</span><strong>${escapeHtml(provenance.last_slm_run_at || "pending")}</strong></div>
          <div class="kv-row"><span>Next Question</span><strong>${escapeHtml(priority.next_question_goal || "hold steady")}</strong></div>
          <div class="kv-row"><span>Question Style</span><strong>${escapeHtml(priority.question_style || "short_open")}</strong></div>
          <div class="kv-row"><span>Location Gate</span><strong>${escapeHtml(locationGate.search_allowed ? "search allowed" : "search guarded")}</strong></div>
          <div class="kv-row"><span>Location Next Step</span><strong>${escapeHtml(priority.location_followup_kind || "none")}</strong></div>
        </div>
        <div class="ticket-summary">
          <div class="section-label">Confirmed Hard Facts</div>
          ${
            confirmedFacts.length
              ? `<ul>${confirmedFacts.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
              : `<p>No confirmed hard facts yet.</p>`
          }
        </div>
        <div class="ticket-summary">
          <div class="section-label">Soft Estimates</div>
          ${
            softGuesses.length
              ? `<ul>${softGuesses.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
              : `<p>No soft estimates yet.</p>`
          }
        </div>
        <div class="ticket-summary">
          <div class="section-label">Still Missing</div>
          ${
            (priority.missing_fields || []).length
              ? `<p>${escapeHtml((priority.missing_fields || []).map(humanizeField).join(", "))}</p>`
              : `<p>No major hard-fact gaps right now.</p>`
          }
        </div>
        <div class="ticket-summary">
          <div class="section-label">Location State</div>
          <p>${escapeHtml(
            [
              locationGate.search_reason || "pending",
              locationGate.candidate_text || null,
              locationGate.candidate_only ? "candidate only" : null,
              locationGate.needs_confirmation ? "needs confirmation" : null,
              locationGate.confirmed ? "confirmed" : null,
            ]
              .filter(Boolean)
              .join(" · ")
          )}</p>
        </div>
        <div class="ticket-summary">
          <div class="section-label">Location Follow-Up</div>
          <p>${escapeHtml(priority.location_followup_prompt || "No location follow-up queued.")}</p>
        </div>
      `;
      return;
    }
    if (!latestTurn && !Object.keys(merged).length) {
      triagePanelEl.innerHTML = `
        <article class="entry event">
          <div class="body">No triage state yet.</div>
        </article>
      `;
      return;
    }
    triagePanelEl.innerHTML = `
      <div class="kv-list">
        <div class="kv-row"><span>Engine</span><strong>${escapeHtml(triageMeta.selected_engine || latestTurn?.selected_engine || "pending")}</strong></div>
        <div class="kv-row"><span>Runtime</span><strong>${escapeHtml(triageMeta.runtime_provider || latestTurn?.runtime_provider || "pending")}</strong></div>
        <div class="kv-row"><span>Version</span><strong>${escapeHtml(String(triageMeta.version || latestTurn?.version || 0))}</strong></div>
        <div class="kv-row"><span>Dispatchable</span><strong>${escapeHtml(String(triageMeta.dispatchable ?? latestTurn?.dispatchable ?? false))}</strong></div>
        <div class="kv-row"><span>Autonomy Allowed</span><strong>${escapeHtml(String(triageMeta.autonomy_allowed ?? latestTurn?.autonomy_allowed ?? false))}</strong></div>
        <div class="kv-row"><span>STT Active</span><strong>${escapeHtml(sttMeta.active_provider || "gradium")}</strong></div>
        <div class="kv-row"><span>STT Compare Mode</span><strong>${escapeHtml((sttMeta.continuous_compare ?? false) ? "continuous" : "rescue-only")}</strong></div>
        <div class="kv-row"><span>STT Elapsed</span><strong>${escapeHtml(String(sttMeta.shadow_elapsed_s ?? 0))} s</strong></div>
      </div>
      <div class="ticket-summary">
        <div class="section-label">Latest Triage Delta</div>
        <pre>${escapeHtml(JSON.stringify(latestTurn?.latest_triage_delta || {}, null, 2))}</pre>
      </div>
      <div class="ticket-summary">
        <div class="section-label">Merged Triage State</div>
        <pre>${escapeHtml(JSON.stringify(merged, null, 2))}</pre>
      </div>
      <div class="ticket-summary">
        <div class="section-label">Missing / Unknown Fields</div>
        <p>${escapeHtml((triageMeta.missing_or_unknown_fields || latestTurn?.missing_or_unknown_fields || []).join(", ") || "None")}</p>
      </div>
      <div class="ticket-summary">
        <div class="section-label">Rule Overrides</div>
        ${
          overrides.length
            ? `<pre>${escapeHtml(JSON.stringify(overrides, null, 2))}</pre>`
            : `<p>No hard overrides triggered.</p>`
        }
      </div>
      <div class="ticket-summary">
        <div class="section-label">STT Rescue</div>
        ${
          latestRescue
            ? `<pre>${escapeHtml(JSON.stringify(latestRescue, null, 2))}</pre>`
            : `<p>No rescue events yet.</p>`
        }
      </div>
      <div class="ticket-summary">
        <div class="section-label">STT Provider Scores</div>
        ${
          sttMeta.provider_stats
            ? `<pre>${escapeHtml(JSON.stringify(sttMeta.provider_stats, null, 2))}</pre>`
            : `<p>No provider scores yet.</p>`
        }
      </div>
      <div class="ticket-summary">
        <div class="section-label">STT Switches</div>
        ${
          sttMeta.switch_events && sttMeta.switch_events.length
            ? `<pre>${escapeHtml(JSON.stringify(sttMeta.switch_events, null, 2))}</pre>`
            : `<p>No provider switch yet.</p>`
        }
      </div>
      <div class="ticket-summary">
        <div class="section-label">Handoff Packet</div>
        ${
          handoff
            ? `<pre>${escapeHtml(JSON.stringify(handoff, null, 2))}</pre>`
            : `<p>No handoff packet yet.</p>`
        }
      </div>
    `;
  }

  function latestToolCall(toolCalls, name) {
    return [...toolCalls].reverse().find((item) => item.name === name);
  }

  function latestToolCallAny(toolCalls, names) {
    const allowed = new Set(names);
    return [...toolCalls].reverse().find((item) => allowed.has(item.name));
  }

  function transcriptTurns(session, role) {
    return session?.client?.transcripts?.[role] || [];
  }

  function combinedTranscriptText(session, role) {
    return transcriptTurns(session, role)
      .map((item) => item.text)
      .filter(Boolean)
      .join(" ")
      .trim();
  }

  function inferTranscriptIssue(session) {
    const text = `${combinedTranscriptText(session, "user")} ${combinedTranscriptText(session, "agent")}`.toLowerCase();
    if ((text.includes("daughter") || text.includes("son") || text.includes("child")) && (text.includes("lost") || text.includes("cannot find") || text.includes("can't find") || text.includes("missing"))) {
      return "Missing child";
    }
    if (text.includes("not breathing") || text.includes("unconscious")) return "Medical emergency";
    if (text.includes("fire") || text.includes("smoke")) return "Fire";
    if (text.includes("bleeding") || text.includes("injured")) return "Medical emergency";
    if (text.includes("crash") || text.includes("accident") || text.includes("collision")) return "Traffic incident";
    if (text.includes("weapon") || text.includes("gun") || text.includes("knife") || text.includes("hostage")) return "Police incident";
    return "Pending";
  }

  function inferTranscriptPriority(session, issueLabel) {
    const text = `${combinedTranscriptText(session, "user")} ${combinedTranscriptText(session, "agent")}`.toLowerCase();
    if (issueLabel === "Missing child") return "HIGH";
    if (text.includes("not breathing") || text.includes("unconscious") || text.includes("fire") || text.includes("hostage")) return "CRITICAL";
    if (text.includes("bleeding") || text.includes("trapped") || text.includes("weapon")) return "HIGH";
    if (issueLabel !== "Pending") return "MEDIUM";
    return "Pending";
  }

  function dispatchLaneForPriority(priority) {
    const value = String(priority || "").toUpperCase();
    return {
      CRITICAL: "lights_and_sirens",
      HIGH: "urgent",
      MEDIUM: "standard",
      LOW: "queued",
    }[value] || "Pending";
  }

  function lastSubstantiveLocationClue(session) {
    const userTurns = transcriptTurns(session, "user");
    const locationPattern = /\b(station|bahnhof|park|platz|playground|campus|hospital|metro|street|strasse|straße|road|junction|entrance|berlin)\b/i;
    for (let index = userTurns.length - 1; index >= 0; index -= 1) {
      const text = String(userTurns[index]?.text || "").trim();
      if (text.length >= 6 && locationPattern.test(text)) {
        return text.replace(/\s+/g, " ");
      }
    }
    return null;
  }

  function lastConfirmedAgentLocation(session) {
    const agentTurns = transcriptTurns(session, "agent");
    const userTurns = transcriptTurns(session, "user");
    const yesPattern = /^(yes|yeah|yep|correct|that'?s right)\b/i;
    for (let index = agentTurns.length - 1; index >= 0; index -= 1) {
      const agentTurn = agentTurns[index];
      const agentText = String(agentTurn?.text || "").trim();
      let candidate = null;
      let match = agentText.match(/Did you mean (.+?)\?/i);
      if (match) {
        candidate = match[1].trim();
      } else {
        match = agentText.match(/^(.+?)\.\s*Is that right\?/i);
        if (match) candidate = match[1].trim();
      }
      if (!candidate) continue;
      const agentAt = agentTurn?.at ? Date.parse(agentTurn.at) : NaN;
      for (let userIndex = userTurns.length - 1; userIndex >= 0; userIndex -= 1) {
        const userTurn = userTurns[userIndex];
        const userText = String(userTurn?.text || "").trim();
        if (!yesPattern.test(userText)) continue;
        const userAt = userTurn?.at ? Date.parse(userTurn.at) : NaN;
        if (
          Number.isFinite(agentAt) &&
          Number.isFinite(userAt) &&
          Math.abs(userAt - agentAt) <= 2000
        ) {
          return candidate;
        }
        if (Number.isFinite(agentAt) && Number.isFinite(userAt) && userAt >= agentAt && userAt - agentAt <= 12000) {
          return candidate;
        }
      }
    }
    return null;
  }

  function transcriptLocationFallback(session) {
    const confirmed = lastConfirmedAgentLocation(session);
    if (confirmed) {
      return { text: confirmed, confidence: "confirmed by caller", source: "dialogue_confirmation" };
    }
    const clue = lastSubstantiveLocationClue(session);
    if (clue) {
      return { text: clue, confidence: "spoken clue", source: "caller_transcript" };
    }
    return { text: null, confidence: null, source: null };
  }

  function deriveDashboardState(session) {
    const serverMode = normalizeDispatchMode(session.server?.live_dispatch_mode || session.server?.triage_engine);
    const toolCalls = session.tool_calls || [];
    const dispatchServicesState = session.dispatch_services || {};
    const sharedLedger = session.shared_ledger || {};
    const hardFacts = sharedLedger.hard_facts || {};
    const locationGate = sharedLedger.location_gate || {};
    const resolveNoteCall = latestToolCall(toolCalls, "resolve_location_note");
    const nearbyContextCall = latestToolCall(toolCalls, "nearby_context");
    const checklistCall = latestToolCall(toolCalls, "checklist_by_incident");
    const handoffBriefCall = latestToolCall(toolCalls, "build_handoff_brief");
    const ticketCall = latestToolCall(toolCalls, "create_incident_ticket");
    const validateCall = latestToolCall(toolCalls, "validate_address");
    const lookupCall = latestToolCall(toolCalls, "lookup_address");
    const validatedLocation = validateCall?.result?.candidate_only ? null : validateCall?.result || null;
    const lookedUpLocation = lookupCall?.result?.candidate_only ? null : lookupCall?.result || null;
    const candidateLocationResult =
      validateCall?.result?.candidate_only ? validateCall?.result : lookupCall?.result?.candidate_only ? lookupCall?.result : null;
    const ticketResult = ticketCall?.result || {};
    const ticketArgs = ticketCall?.args || {};
    const transcriptIssue = inferTranscriptIssue(session);
    const transcriptLocation = transcriptLocationFallback(session);

    const priority =
      ticketResult.priority ||
      inferTranscriptPriority(session, transcriptIssue) ||
      "Pending";
    const issueType =
      ticketResult.issue_type ||
      ticketArgs.issue_type ||
      ((hardFacts.issue_cues || []).length ? (hardFacts.issue_cues || []).map(titleCase).join(", ") : null) ||
      transcriptIssue ||
      "Pending";
    const location =
      ticketResult.address ||
      nearbyContextCall?.result?.normalized_address ||
      validatedLocation?.normalized_address ||
      lookedUpLocation?.normalized_address ||
      hardFacts.location_candidate ||
      locationGate.candidate_text ||
      hardFacts.location_note ||
      resolveNoteCall?.result?.anchor_location ||
      transcriptLocation.text ||
      resolveNoteCall?.result?.normalized_note ||
      candidateLocationResult?.normalized_address ||
      validateCall?.args?.address_text ||
      lookupCall?.args?.address_text ||
      "Pending";
    const lat =
      nearbyContextCall?.result?.lat ??
      validatedLocation?.lat ??
      lookedUpLocation?.lat ??
      null;
    const lon =
      nearbyContextCall?.result?.lon ??
      validatedLocation?.lon ??
      lookedUpLocation?.lon ??
      null;
    const ticketStatus = ticketResult.status || "Not created";
    const dispatchLane = dispatchLaneForPriority(priority);
    const toolCount = toolCalls.length;
    const mapCandidates =
      nearbyContextCall?.result?.candidates ||
      lookedUpLocation?.candidates ||
      validatedLocation?.candidates ||
      [];
    const mapSource =
      nearbyContextCall?.result?.reason ||
      validatedLocation?.source ||
      lookedUpLocation?.source ||
      (serverMode === "slm" ? locationGate.search_reason : null) ||
      candidateLocationResult?.source ||
      transcriptLocation.source ||
      null;
    const mapConfidence =
      validatedLocation?.confidence ||
      lookedUpLocation?.confidence ||
      (serverMode === "slm" ? (locationGate.confirmed ? "confirmed" : locationGate.candidate_only ? "needs confirmation" : null) : null) ||
      (candidateLocationResult ? "needs confirmation" : null) ||
      transcriptLocation.confidence ||
      null;
    const hasPin = lat != null && lon != null;

    const labels = [
      ["Issue", issueType !== "Pending" ? issueType : null],
      ["Lane", dispatchLane !== "Pending" ? dispatchLane : null],
      ["Next", checklistCall?.result?.next_question_goal],
      ["Handoff", handoffBriefCall?.result?.status],
      ["Geo", mapConfidence || (hasPin ? "pinned" : "unresolved")],
    ].filter(([, value]) => value);

    return {
      priority,
      issueType,
      location,
      lat,
      lon,
      ticketStatus,
      dispatchLane,
      toolCount,
      mapCandidates,
      mapSource,
      mapConfidence,
      locationNeedsConfirmation: Boolean(candidateLocationResult),
      hasPin,
      labels,
      dispatchServices: dispatchServicesState.services || {},
      dispatchSummary: dispatchServicesState.summary || null,
      humanMonitoring: Boolean(dispatchServicesState.human_monitoring),
      monitorName: dispatchServicesState.monitor_name || null,
      seriousEmergency: Boolean(dispatchServicesState.serious_emergency),
      dispatchAnnouncement: dispatchServicesState.announcement_line || null,
      serverMode,
      sharedLedger,
      resolveNoteCall,
      nearbyContextCall,
      checklistCall,
      handoffBriefCall,
      ticketCall,
      toolCalls,
      serverStatus: session.server?.status || "waiting",
    };
  }

  function renderSnapshot(session) {
    const state = deriveDashboardState(session);
    dispatchMetricEl.textContent = state.ticketStatus;
    snapshotGridEl.innerHTML = `
      <article class="snapshot-card priority-${String(state.priority).toLowerCase()}">
        <span class="snapshot-label">Priority</span>
        <strong>${escapeHtml(state.priority)}</strong>
      </article>
      <article class="snapshot-card">
        <span class="snapshot-label">Issue</span>
        <strong>${escapeHtml(state.issueType)}</strong>
      </article>
      <article class="snapshot-card location-card">
        <span class="snapshot-label">Location</span>
        <strong>${escapeHtml(state.location)}</strong>
      </article>
      <article class="snapshot-card">
        <span class="snapshot-label">Pin</span>
        <strong>${escapeHtml(state.hasPin ? "Landed" : "Unresolved")}</strong>
      </article>
      <article class="snapshot-card">
        <span class="snapshot-label">Geo Confidence</span>
        <strong>${escapeHtml(state.mapConfidence || "Pending")}</strong>
      </article>
      <article class="snapshot-card">
        <span class="snapshot-label">Dispatch Lane</span>
        <strong>${escapeHtml(state.dispatchLane)}</strong>
      </article>
      <article class="snapshot-card">
        <span class="snapshot-label">Ticket</span>
        <strong>${escapeHtml(state.ticketStatus)}</strong>
      </article>
      <article class="snapshot-card">
        <span class="snapshot-label">Tool Calls</span>
        <strong>${escapeHtml(String(state.toolCount))}</strong>
      </article>
    `;
    updateMap(state);
    renderToolChain(session);
    renderServicePanel(state);

    if (!state.labels.length) {
      labelChipsEl.innerHTML = `<span class="chip pending">Waiting for labels</span>`;
    } else {
      labelChipsEl.innerHTML = state.labels
        .map(
          ([label, value]) =>
            `<span class="chip"><span class="chip-label">${escapeHtml(label)}</span>${escapeHtml(value)}</span>`
        )
        .join("");
    }

    if (!state.ticketCall) {
      ticketPanelEl.innerHTML = `
        <article class="entry event">
          <div class="body">No incident ticket yet.</div>
        </article>
      `;
    } else {
      const ticket = state.ticketCall.result || {};
      const notes = (ticket.notes || []).map((note) => `<li>${escapeHtml(note)}</li>`).join("");
      ticketPanelEl.innerHTML = `
        <div class="kv-list">
          <div class="kv-row"><span>Status</span><strong>${escapeHtml(ticket.status || "pending")}</strong></div>
          <div class="kv-row"><span>Priority</span><strong>${escapeHtml(ticket.priority || "pending")}</strong></div>
          <div class="kv-row"><span>Issue Type</span><strong>${escapeHtml(ticket.issue_type || "pending")}</strong></div>
          <div class="kv-row"><span>Address</span><strong>${escapeHtml(ticket.address || "pending")}</strong></div>
          <div class="kv-row"><span>Schema</span><strong>${escapeHtml(ticket.schema_version || "n/a")}</strong></div>
        </div>
        <div class="ticket-summary">
          <div class="section-label">Caller Summary</div>
          <p>${escapeHtml(ticket.caller_summary || "Not available yet.")}</p>
        </div>
        <div class="ticket-summary">
          <div class="section-label">Notes</div>
          ${notes ? `<ul class="note-list">${notes}</ul>` : `<p>No notes yet.</p>`}
        </div>
      `;
    }

    if (!state.toolCalls.length) {
      toolLogEl.innerHTML = `
        <article class="entry event">
          <div class="body">No tool calls yet.</div>
        </article>
      `;
      return;
    }

    toolLogEl.innerHTML = [...state.toolCalls]
      .reverse()
      .map((toolCall) => {
        const result = toolCall.result || {};
        const error = toolCall.error;
        return `
          <article class="tool-entry ${error ? "error" : "ok"}">
            <div class="tool-head">
              <div>
                <strong>${escapeHtml(toolCall.name)}</strong>
                <p>${escapeHtml(summarizeToolCall(toolCall))}</p>
              </div>
              <span class="tool-at">${escapeHtml(toolCall.at || "")}</span>
            </div>
            <details>
              <summary>Inspect payload</summary>
              <div class="tool-payload">
                <div>
                  <div class="section-label">Args</div>
                  <pre>${escapeHtml(JSON.stringify(toolCall.args || {}, null, 2))}</pre>
                </div>
                <div>
                  <div class="section-label">${error ? "Error" : "Result"}</div>
                  <pre>${escapeHtml(JSON.stringify(error || result, null, 2))}</pre>
                </div>
              </div>
            </details>
          </article>
        `;
      })
      .join("");
  }

  async function refreshSessionDetail() {
    if (!sessionId) return;
    const session = await fetch(`/api/sessions/${sessionId}`).then((res) => res.json());
    const activeProvider = session?.stt_rescue_meta?.active_provider || "gradium";
    if (activeProvider !== lastActiveTranscriptProvider) {
      logEvent(`stt provider switched ${lastActiveTranscriptProvider} -> ${activeProvider}`);
      lastActiveTranscriptProvider = activeProvider;
    }
    latestSession = session;
    const dashboardState = deriveDashboardState(session);
    renderSnapshot(session);
    renderOperatorDesk(session, dashboardState);
    renderTriagePanel(session);
    setMemoryPanel(session);
  }

  function startBackgroundLoops() {
    if (sessionPollHandle) clearInterval(sessionPollHandle);
    if (syncHandle) clearInterval(syncHandle);

    sessionPollHandle = setInterval(() => {
      refreshSessionDetail().catch(() => {});
    }, 1200);

    syncHandle = setInterval(() => {
      syncSessionReport("live").catch(() => {});
    }, 2000);
  }

  function stopBackgroundLoops() {
    if (sessionPollHandle) {
      clearInterval(sessionPollHandle);
      sessionPollHandle = null;
    }
    if (syncHandle) {
      clearInterval(syncHandle);
      syncHandle = null;
    }
  }

  function resetDashboard() {
    sessionMetricEl.textContent = "Not started";
    dispatchMetricEl.textContent = "Waiting";
    severityHeroEl.className = "severity-hero severity-green";
    severityScoreEl.textContent = "0 / 100";
    severitySubtextEl.textContent = "Waiting for a live incident.";
    takeoverBtn.textContent = "Human Standby";
    takeoverBtn.className = "button takeover-button severity-green";
    takeoverBtn.disabled = true;
    operatorReportEl.innerHTML = `
      <article class="entry event">
        <div class="body">Start a call to populate the human handoff brief.</div>
      </article>
    `;
    snapshotGridEl.innerHTML = `
      <article class="snapshot-card">
        <span class="snapshot-label">Priority</span>
        <strong>Pending</strong>
      </article>
      <article class="snapshot-card">
        <span class="snapshot-label">Issue</span>
        <strong>Pending</strong>
      </article>
      <article class="snapshot-card location-card">
        <span class="snapshot-label">Location</span>
        <strong>Pending</strong>
      </article>
      <article class="snapshot-card">
        <span class="snapshot-label">Pin</span>
        <strong>Unresolved</strong>
      </article>
      <article class="snapshot-card">
        <span class="snapshot-label">Geo Confidence</span>
        <strong>Pending</strong>
      </article>
      <article class="snapshot-card">
        <span class="snapshot-label">Dispatch Lane</span>
        <strong>Pending</strong>
      </article>
      <article class="snapshot-card">
        <span class="snapshot-label">Ticket</span>
        <strong>Not created</strong>
      </article>
      <article class="snapshot-card">
        <span class="snapshot-label">Tool Calls</span>
        <strong>0</strong>
      </article>
    `;
    labelChipsEl.innerHTML = `<span class="chip pending">Waiting for labels</span>`;
    triagePanelEl.innerHTML = `
      <article class="entry event">
        <div class="body">No triage state yet.</div>
      </article>
    `;
    ticketPanelEl.innerHTML = `
      <article class="entry event">
        <div class="body">No incident ticket yet.</div>
      </article>
    `;
    toolChainEl.innerHTML = `
      <article class="entry event">
        <div class="body">No deterministic assist chain activity yet.</div>
      </article>
    `;
    servicePanelEl.innerHTML = `
      <article class="service-card service-card-pending">
        <div class="service-top">
          <strong>Services</strong>
          <span class="service-state">Pending</span>
        </div>
        <p>Start a call to populate the service board.</p>
        <small>Police, ambulance, and fire updates will appear here.</small>
      </article>
    `;
    toolLogEl.innerHTML = `
      <article class="entry event">
        <div class="body">No tool calls yet.</div>
      </article>
    `;
    setMemoryPanel(null);
    clearMapState();
  }

  async function startDemo() {
    const dispatchMode = getSelectedDispatchMode();
    connectBtn.disabled = true;
    if (dispatchModeSelect) {
      dispatchModeSelect.disabled = true;
    }
    reportSent = false;
    sessionId = crypto.randomUUID();
    sessionStartedAt = new Date().toISOString();
    clearTranscriptBuffers();
    userTranscriptChunks = [];
    agentTranscriptChunks = [];
    userTranscripts = [];
    agentTranscripts = [];
    eventEntries = [];
    maxBufferMs = 0;
    latestSession = null;
    interruptCount = 0;
    lastAdaptiveAt = 0;
    recoveryModeArmed = false;
    assistantTurnActive = false;
    pendingTriageUpdate = null;
    pendingLedgerUpdate = null;
    pendingDispatchUpdate = null;
    latestTriageContext = null;
    latestLedgerContext = null;
    latestDispatchContext = null;
    lastTriageVersionSent = 0;
    lastLedgerVersionSent = 0;
    lastDispatchVersionSent = 0;
    lastRescueIndexSeen = -1;
    lastActiveTranscriptProvider = "gradium";
    humanTakeoverEngaged = false;
    stickySummaryText = null;
    pendingHandoffResumePrompt = null;
    eventLogEl.innerHTML = "";
    resetDashboard();
    renderDialogueStreams();
    sessionMetricEl.textContent = sessionId;
    setStatus("Connecting...", "idle");
    dispatchMetricEl.textContent = dispatchMode === "llm_only" ? "Listening · LLM only" : "Listening · SLM + LLM";
    logEvent("requesting microphone access");
    logEvent(`dispatch mode selected: ${dispatchModeLabel(dispatchMode)}`);

    try {
      currentAudioConfig = await fetch("/api/audio-config").then((res) => res.json());
      player = await createPlayer(currentAudioConfig);
      ws = new WebSocket(getWsUrl());
      ws.binaryType = "blob";

      ws.onopen = () => {
        ws.send(
          JSON.stringify({
            type: "start",
            session_id: sessionId,
            triage_mode: dispatchMode,
            client: {
              user_agent: navigator.userAgent,
              platform: navigator.platform,
              triage_mode: dispatchMode,
            },
          })
        );
        setStatus("Live", "live");
        dispatchMetricEl.textContent = dispatchMode === "llm_only" ? "Listening · LLM only" : "Listening · SLM + LLM";
        disconnectBtn.disabled = false;
        logEvent("websocket connected");
        startBackgroundLoops();
        refreshSessionDetail().catch(() => {});
      };

      ws.onmessage = (event) => {
        if (humanTakeoverEngaged && event.data instanceof Blob) {
          return;
        }
        player.handleMessage(event.data);
      };

      ws.onerror = () => {
        logEvent("websocket error", "error");
        setStatus("Error", "error");
      };

      ws.onclose = (event) => {
        logEvent(`websocket closed (${event.code})`);
        stopBackgroundLoops();
        finalizePendingUser("close");
        finalizePendingAgent("close");
        flushSessionReport("closed");
        cleanup();
        refreshSessionDetail().catch(() => {});
      };
    } catch (error) {
      logEvent(error.message || String(error), "error");
      setStatus("Error", "error");
      flushSessionReport("setup_error");
      cleanup();
    }
  }

  function cleanup() {
    stopBackgroundLoops();
    clearTranscriptBuffers();
    if (dispatchModeSelect) {
      dispatchModeSelect.disabled = false;
    }
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.close();
    }
    ws = null;
    if (player) {
      stopPcmCapture();
      player.stop();
    }
    player = null;
    connectBtn.disabled = false;
    disconnectBtn.disabled = true;
    bufferMetricEl.textContent = "0 ms";
    if (statusEl.textContent !== "Error") {
      setStatus("Idle", "idle");
    }
  }

  function stopDemo() {
    flushPcmPending(true);
    finalizePendingUser("stop");
    finalizePendingAgent("stop");
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "stop" }));
      ws.close();
    }
    logEvent("call stopped");
    flushSessionReport("stopped");
    cleanup();
    refreshSessionDetail().catch(() => {});
  }

  connectBtn.addEventListener("click", startDemo);
  disconnectBtn.addEventListener("click", stopDemo);
  if (dispatchModeSelect) {
    const storedMode = normalizeDispatchMode(window.localStorage.getItem(DISPATCH_MODE_STORAGE_KEY));
    dispatchModeSelect.value = storedMode;
    dispatchModeSelect.addEventListener("change", () => {
      const nextMode = getSelectedDispatchMode();
      window.localStorage.setItem(DISPATCH_MODE_STORAGE_KEY, nextMode);
      logEvent(`dispatch mode ready: ${dispatchModeLabel(nextMode)}`);
    });
  }
  clearBtn.addEventListener("click", () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      logEvent("stop the call before clearing the console", "error");
      return;
    }
    eventLogEl.innerHTML = "";
    clearTranscriptBuffers();
    userTranscriptChunks = [];
    agentTranscriptChunks = [];
    userTranscripts = [];
    agentTranscripts = [];
    eventEntries = [];
    sessionId = null;
    sessionStartedAt = null;
    latestSession = null;
    reportSent = false;
    lastActiveTranscriptProvider = "gradium";
    humanTakeoverEngaged = false;
    stickySummaryText = null;
    pendingHandoffResumePrompt = null;
    latestLedgerContext = null;
    lastLedgerVersionSent = 0;
    pendingLedgerUpdate = null;
    resetDashboard();
    renderDialogueStreams();
  });

  takeoverBtn.addEventListener("click", () => {
    if (!sessionId || !latestSession) {
      logEvent("start a call before using human takeover", "error");
      return;
    }
    humanTakeoverEngaged = !humanTakeoverEngaged;
    pendingHandoffResumePrompt = humanTakeoverEngaged ? null : HANDOFF_RESUME_PROMPT;
    sendTriageConfig(humanTakeoverEngaged ? "human_takeover_engaged" : "human_takeover_cleared");
    logEvent(
      humanTakeoverEngaged
        ? "human takeover engaged"
        : `handover returned to agent · next question: ${HANDOFF_RESUME_PROMPT}`
    );
    renderOperatorDesk(latestSession, deriveDashboardState(latestSession));
  });

  window.addEventListener("beforeunload", () => {
    finalizePendingUser("unload");
    finalizePendingAgent("unload");
    flushSessionReport("unloaded");
    stopBackgroundLoops();
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.close();
    }
    if (player) {
      stopPcmCapture();
      player.stop();
    }
  });

  initMap();
  resetDashboard();
  renderDialogueStreams();
})();
