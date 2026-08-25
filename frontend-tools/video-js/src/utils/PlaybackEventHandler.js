import BehaviorTracker from './BehaviorTracker';

/**
 * PlaybackEventHandler - Utility for handling video player playback events
 *
 * Provides comprehensive playback event handling for video players including:
 * - Play event handling with seek indicators and embed player visibility
 * - Pause event handling with poster management
 * - Quality change detection to prevent unnecessary indicators
 */

class PlaybackEventHandler {
    constructor(playerRef, customComponents = null, options = {}) {
        this.playerRef = playerRef;
        this.customComponents = customComponents;
        this.options = {
            isEmbedPlayer: false,
            showSeekIndicators: true,
            ...options,
        };
        this.eventHandlers = {};
        this.isActive = false;
        this.behaviorTracker = null;
    }

    /**
     * Handle play event
     * Shows play indicator and manages embed player visibility
     */
    handlePlayEvent = () => {
        const player = this.playerRef.current;
        if (!player) return;

        // Only show play indicator if not changing quality and indicators are enabled
        if (
            !player.isChangingQuality &&
            this.options.showSeekIndicators &&
            this.customComponents?.current?.seekIndicator
        ) {
            this.customComponents.current.seekIndicator.show('play');
        }

        // For embed players, ensure video becomes visible when playing
        if (this.options.isEmbedPlayer) {
            this.handleEmbedPlayerVisibility('play');
        }
    };

    /**
     * Handle pause event
     * Shows pause indicator and manages embed player poster visibility
     */
    handlePauseEvent = () => {
        const player = this.playerRef.current;
        if (!player) return;

        // Only show pause indicator if not changing quality and indicators are enabled
        if (
            !player.isChangingQuality &&
            this.options.showSeekIndicators &&
            this.customComponents?.current?.seekIndicator
        ) {
            this.customComponents.current.seekIndicator.show('pause');
        }

        // For embed players, show poster when paused at beginning
        if (this.options.isEmbedPlayer && player.currentTime() === 0) {
            this.handleEmbedPlayerVisibility('pause');
        }
    };

    /**
     * Handle embed player visibility for play/pause states
     * @param {string} action - 'play' or 'pause'
     */
    handleEmbedPlayerVisibility(action) {
        const player = this.playerRef.current;
        if (!player) return;

        const playerEl = player.el();
        const videoEl = playerEl.querySelector('video');
        const posterEl = playerEl.querySelector('.vjs-poster');
        const bigPlayButton = player.getChild('bigPlayButton');

        if (action === 'play') {
            // Make video visible and hide poster
            if (videoEl) {
                videoEl.style.opacity = '1';
            }
            if (posterEl) {
                posterEl.style.opacity = '0';
            }
            // Hide big play button when video starts playing
            if (bigPlayButton) {
                bigPlayButton.hide();
            }
        } else if (action === 'pause') {
            // Hide video and show poster
            if (videoEl) {
                videoEl.style.opacity = '0';
            }
            if (posterEl) {
                posterEl.style.opacity = '1';
            }
            // Show big play button when paused at beginning
            if (bigPlayButton) {
                bigPlayButton.show();
            }
        }
    }

    /**
     * Initialize playback event handling
     */
    init() {
        if (this.isActive) {
            console.warn('PlaybackEventHandler is already active');
            return;
        }

        const player = this.playerRef.current;
        if (!player) {
            console.error('Player reference is not available');
            return;
        }

        // Add event listeners
        player.on('play', this.handlePlayEvent);
        player.on('pause', this.handlePauseEvent);

        // Store event handlers for cleanup
        this.eventHandlers = {
            play: this.handlePlayEvent,
            pause: this.handlePauseEvent,
        };

        this.isActive = true;

        if (!this.options.isEmbedPlayer && typeof window !== 'undefined') {
            const videoId = window.MEDIA_DATA?.data?.friendly_token || new URLSearchParams(window.location.search).get('m');
            this.behaviorTracker = new BehaviorTracker(player, videoId);
            this.behaviorTracker.init();
        }
    }

    /**
     * Clean up playback event handling
     */
    destroy() {
        if (!this.isActive) {
            return;
        }

        const player = this.playerRef.current;
        if (player && this.eventHandlers) {
            // Remove event listeners
            Object.entries(this.eventHandlers).forEach(([event, handler]) => {
                player.off(event, handler);
            });
        }

        this.eventHandlers = {};
        this.isActive = false;
        if (this.behaviorTracker) {
            this.behaviorTracker.destroy();
            this.behaviorTracker = null;
        }
    }

    /**
     * Update options
     * @param {Object} newOptions - New options to merge
     */
    updateOptions(newOptions) {
        this.options = { ...this.options, ...newOptions };
    }

    /**
     * Update player reference
     * @param {Object} newPlayerRef - New player reference
     */
    updatePlayerRef(newPlayerRef) {
        this.playerRef = newPlayerRef;
    }

    /**
     * Update custom components reference
     * @param {Object} newCustomComponents - New custom components reference
     */
    updateCustomComponents(newCustomComponents) {
        this.customComponents = newCustomComponents;
    }

    /**
     * Enable or disable seek indicators
     * @param {boolean} enabled - Whether to show seek indicators
     */
    setSeekIndicatorsEnabled(enabled) {
        this.options.showSeekIndicators = enabled;
    }

    /**
     * Set embed player mode
     * @param {boolean} isEmbed - Whether this is an embed player
     */
    setEmbedPlayerMode(isEmbed) {
        this.options.isEmbedPlayer = isEmbed;
    }
}

export default PlaybackEventHandler;
