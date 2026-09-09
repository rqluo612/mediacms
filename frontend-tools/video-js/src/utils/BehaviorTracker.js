const uuid = () => {
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (char) => {
        const value = Math.floor(Math.random() * 16);
        return (char === 'x' ? value : (value & 0x3) | 0x8).toString(16);
    });
};

const csrfToken = () => {
    const item = document.cookie.split('; ').find((cookie) => cookie.startsWith('csrftoken='));
    return item ? decodeURIComponent(item.split('=').slice(1).join('=')) : '';
};

class BehaviorTracker {
    constructor(player, videoId) {
        this.player = player;
        this.videoId = videoId;
        this.sessionId = null;
        this.interactionId = null;
        this.sequence = 0;
        this.watchDuration = 0;
        this.maxPosition = 0;
        this.replayCount = 0;
        this.playingSince = null;
        this.ended = false;
        this.firstPlay = true;
        this.pendingEvents = [];
        this.pendingEndReason = null;
        this.destroyed = false;
        this.handlers = {};
        this.initDelay = null;
    }

    request(path, method, body, keepalive = false) {
        return fetch(path, {
            method,
            credentials: 'same-origin',
            keepalive,
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            body: JSON.stringify(body),
        }).then(async (response) => {
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                const error = new Error(`Behavior API ${response.status}`);
                error.code = data.code;
                throw error;
            }
            return data;
        });
    }

    nextSequence() {
        this.sequence += 1;
        return this.sequence;
    }

    updateWatchClock() {
        const now = performance.now();
        if (this.playingSince !== null) {
            this.watchDuration += Math.max(0, (now - this.playingSince) / 1000);
        }
        this.playingSince = !this.player.paused() && !document.hidden ? now : null;
        this.maxPosition = Math.max(this.maxPosition, this.player.currentTime() || 0);
    }

    totals() {
        this.updateWatchClock();
        return {
            client_sequence: this.nextSequence(),
            client_time: new Date().toISOString(),
            playing: !this.player.paused(),
            visible: !document.hidden,
            current_position: this.player.currentTime() || 0,
            watch_duration: this.watchDuration,
            video_duration: Number.isFinite(this.player.duration()) ? this.player.duration() : null,
            max_play_position: this.maxPosition,
            replay_count: this.replayCount,
        };
    }

    sendEvent(eventType, payload = {}) {
        return this.request(`/api/v1/behavior/interactions/${this.interactionId}/events`, 'POST', {
            event_id: uuid(),
            client_sequence: this.nextSequence(),
            event_type: eventType,
            client_time: new Date().toISOString(),
            payload,
        }).catch(() => {});
    }

    event(eventType, payload = {}) {
        if (this.ended) return Promise.resolve();
        if (!this.interactionId) {
            this.pendingEvents.push({ eventType, payload });
            return Promise.resolve();
        }
        return this.sendEvent(eventType, payload);
    }

    heartbeat() {
        if (!this.interactionId || this.ended) return Promise.resolve();
        return this.request(`/api/v1/behavior/interactions/${this.interactionId}/heartbeat`, 'PATCH', this.totals()).catch(() => {});
    }

    end(reason, keepalive = false) {
        if (this.ended) return Promise.resolve();
        this.updateWatchClock();
        this.ended = true;
        if (!this.interactionId) {
            this.pendingEndReason = reason;
            return Promise.resolve();
        }
        const interactionId = this.interactionId;
        const data = { ...this.totals(), event_id: uuid(), end_reason: reason };
        return this.request(`/api/v1/behavior/interactions/${interactionId}/end`, 'POST', data, keepalive).catch(() => {});
    }

    bindHandlers() {
        const markPlaying = () => {
            this.updateWatchClock();
            if (!this.firstPlay) return;
            this.event('play', { position: this.player.currentTime() || 0, visible: !document.hidden });
            this.firstPlay = false;
        };
        this.handlers.playing = () => {
            const firstPlay = this.firstPlay;
            markPlaying();
            if (!firstPlay) this.event('resume', { position: this.player.currentTime() || 0, visible: !document.hidden });
        };
        this.handlers.timeupdate = () => {
            if (this.firstPlay && !this.player.paused() && (this.player.currentTime() || 0) > 0) markPlaying();
        };
        this.handlers.pause = () => { this.updateWatchClock(); this.event('pause', { position: this.player.currentTime() || 0 }); this.heartbeat(); };
        // EndScreenHandler decides whether a completed playback becomes an
        // automatic "next" transition or a terminal "ended" interaction.
        this.handlers.ended = () => {};
        this.handlers.seeked = () => this.event('seek', { to_position: this.player.currentTime() || 0 });
        this.handlers.visibilitychange = () => { this.updateWatchClock(); this.heartbeat(); };
        this.handlers.pagehide = () => this.end('page_close', true);
        Object.entries(this.handlers).forEach(([name, handler]) => {
            if (name === 'visibilitychange') document.addEventListener(name, handler);
            else if (name === 'pagehide') window.addEventListener(name, handler);
            else this.player.on(name, handler);
        });
    }

    async init() {
        if (!this.videoId || !csrfToken()) return;
        if (this.player._mediaCMSBehaviorTracker && this.player._mediaCMSBehaviorTracker !== this) {
            this.destroyed = true;
            return;
        }
        this.player._mediaCMSBehaviorTracker = this;
        this.bindHandlers();
        await new Promise((resolve) => {
            this.initDelay = window.setTimeout(resolve, 50);
        });
        this.initDelay = null;
        if (this.destroyed) return;
        try {
            let clientSessionId = window.sessionStorage.getItem('mediacms_behavior_session_id');
            if (!clientSessionId) {
                clientSessionId = uuid();
                window.sessionStorage.setItem('mediacms_behavior_session_id', clientSessionId);
            }
            const sessionBody = {
                client_session_id: clientSessionId,
                client_info: { timezone: Intl.DateTimeFormat().resolvedOptions().timeZone, viewport: `${window.innerWidth}x${window.innerHeight}`, app_version: 'mediacms-web' },
            };
            let session;
            try {
                session = await this.request('/api/v1/behavior/sessions', 'POST', sessionBody);
            } catch (error) {
                if (error.code !== 'SESSION_EXPIRED') throw error;
                clientSessionId = uuid();
                window.sessionStorage.setItem('mediacms_behavior_session_id', clientSessionId);
                sessionBody.client_session_id = clientSessionId;
                session = await this.request('/api/v1/behavior/sessions', 'POST', sessionBody);
            }
            this.sessionId = session.session_id;
            const interaction = await this.request('/api/v1/behavior/interactions', 'POST', {
                session_id: this.sessionId,
                video_id: this.videoId,
                entry_context:
                    window.MEDIA_DATA?.data?.behavior_context?.algorithm_id ||
                    (window.MEDIA_DATA?.isPlayList ? 'PLAYLIST' : 'DIRECT'),
                recommendation_context:
                    new URLSearchParams(window.location.search).get('rc') ||
                    window.MEDIA_DATA?.data?.behavior_context?.attribution_token ||
                    null,
            });
            this.interactionId = interaction.interaction_id;
            if (this.destroyed && !this.ended) this.end('navigate', true);
            if (!this.destroyed) {
                window.MediaCMSBehaviorTracker = this;
                window.MediaCMSBehaviorContext = { session_id: this.sessionId, interaction_id: this.interactionId };
                window.MediaCMSRecordBehavior = (eventType, payload) => this.event(eventType, payload);
            }
            await this.sendEvent('exposure', { position: this.player.currentTime() || 0, visible: !document.hidden });
            for (const pending of this.pendingEvents) await this.sendEvent(pending.eventType, pending.payload);
            this.pendingEvents = [];
            if (this.pendingEndReason) {
                const reason = this.pendingEndReason;
                this.pendingEndReason = null;
                const data = { ...this.totals(), event_id: uuid(), end_reason: reason };
                await this.request(`/api/v1/behavior/interactions/${this.interactionId}/end`, 'POST', data, true).catch(() => {});
            }
        } catch {
            return;
        }
        if (this.destroyed) return;
        this.timer = window.setInterval(() => this.heartbeat(), 10000);
    }

    destroy() {
        this.destroyed = true;
        if (this.timer) window.clearInterval(this.timer);
        Object.entries(this.handlers).forEach(([name, handler]) => {
            if (name === 'visibilitychange') document.removeEventListener(name, handler);
            else if (name === 'pagehide') window.removeEventListener(name, handler);
            else this.player.off(name, handler);
        });
        this.end('navigate', true);
        if (this.player._mediaCMSBehaviorTracker === this) delete this.player._mediaCMSBehaviorTracker;
        if (window.MediaCMSBehaviorTracker === this) {
            delete window.MediaCMSBehaviorTracker;
            delete window.MediaCMSBehaviorContext;
            delete window.MediaCMSRecordBehavior;
        }
    }
}

export default BehaviorTracker;
