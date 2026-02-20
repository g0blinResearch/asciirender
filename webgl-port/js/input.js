/**
 * input.js — Keyboard input handler for the browser.
 *
 * Tracks currently-held keys via keydown/keyup events.
 * Much simpler than the Python termios approach.
 */

export class InputManager {
    constructor() {
        /** @type {Set<string>} Currently held keys (lowercase) */
        this.keys = new Set();
        /** @type {Array<string>} Keys pressed this frame (for one-shot actions) */
        this.justPressed = [];

        this._onKeyDown = this._onKeyDown.bind(this);
        this._onKeyUp = this._onKeyUp.bind(this);

        window.addEventListener('keydown', this._onKeyDown);
        window.addEventListener('keyup', this._onKeyUp);
    }

    _onKeyDown(e) {
        const key = this._normalise(e);
        if (!this.keys.has(key)) {
            this.justPressed.push(key);
        }
        this.keys.add(key);
        // Prevent browser defaults for our control keys
        if (['arrowup', 'arrowdown', 'arrowleft', 'arrowright',
             'tab', ' '].includes(key)) {
            e.preventDefault();
        }
    }

    _onKeyUp(e) {
        this.keys.delete(this._normalise(e));
    }

    _normalise(e) {
        // Map to lowercase key names matching our control scheme
        return e.key.toLowerCase();
    }

    /** Call once per frame after processing justPressed. */
    clearFrame() {
        this.justPressed.length = 0;
    }

    /** Check if a key is currently held. */
    isHeld(key) {
        return this.keys.has(key);
    }

    /** Check if any of the given keys are held. */
    anyHeld(...keys) {
        for (const k of keys) {
            if (this.keys.has(k)) return true;
        }
        return false;
    }

    destroy() {
        window.removeEventListener('keydown', this._onKeyDown);
        window.removeEventListener('keyup', this._onKeyUp);
    }
}
