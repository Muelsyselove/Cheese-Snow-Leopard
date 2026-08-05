/**
 * 效果分级管理器 — 自动检测设备性能，选择合适的画质等级
 * basic / high / ultra
 */
class QualityManager {
  constructor() {
    this.level = 'high';
    this.init();
  }

  async init() {
    // 用户保存的偏好优先
    const saved = localStorage.getItem('quality-preference');
    if (saved && saved !== 'auto') {
      this.setLevel(saved);
      return;
    }
    this.detectLevel();
  }

  detectLevel() {
    const supportsWebGL = this.checkWebGL();
    const supportsBackdrop = CSS.supports('backdrop-filter', 'blur(10px)');
    const cores = navigator.hardwareConcurrency || 4;
    const memory = navigator.deviceMemory || 4;

    if (supportsWebGL && cores >= 8 && memory >= 8) {
      this.level = 'ultra';
    } else if (supportsBackdrop && cores >= 4) {
      this.level = 'high';
    } else {
      this.level = 'basic';
    }
    this.applyLevel();
    this._dispatch();
  }

  checkWebGL() {
    try {
      const canvas = document.createElement('canvas');
      return !!(canvas.getContext('webgl2') || canvas.getContext('webgl'));
    } catch { return false; }
  }

  /** 设置画质档位；'auto' 时持久化偏好并重新自动检测 */
  setLevel(level) {
    if (level === 'auto') {
      localStorage.setItem('quality-preference', 'auto');
      this.detectLevel();
      return;
    }
    this.level = level;
    this.applyLevel();
    localStorage.setItem('quality-preference', level);
    this._dispatch();
  }

  /** 当前偏好（auto/basic/high/ultra），供设置页回显 */
  getPreference() {
    return localStorage.getItem('quality-preference') || 'auto';
  }

  _dispatch() {
    window.dispatchEvent(new CustomEvent('qualitychange', {
      detail: { level: this.level }
    }));
  }

  applyLevel() {
    document.documentElement.setAttribute('data-quality', this.level);
    // basic 档隐藏 aurora 背景
    const aurora = document.querySelector('.aurora');
    if (aurora) {
      aurora.style.display = this.level === 'basic' ? 'none' : '';
    }
  }
}
