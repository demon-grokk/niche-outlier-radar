function youtubeRadarApp() {
  return {
    videos: [],
    channels: [],
    matchedChannels: [],
    rawChannels: [],
    rawStats: {},
    loading: false,
    daysBack: 15,
    sortBy: 'smart_signal',
    onlyOutliers: false,
    videoType: 'long',
    collabAdding: false,
    discoveryScanning: false,
    searchQuery: '',
    selectedCategory: 'All',
    categories: ['All', 'AI Agents', 'Automations', 'AI News', 'Developer Tools', 'AGI Research'],
    activeBlueprint: null,
    showChannelModal: false,
    showRawModal: false,
    newChannelInput: '',
    channelSearchQuery: '',
    addingChannel: false,
    syncState: {
      is_running: false,
      current_channel: '',
      channels_completed: 0,
      total_channels: 0
    },
    syncPollInterval: null,

    init() {
      this.loadFeed();
      this.loadChannels();
      this.checkSyncStatus();
    },

    resetFilters() {
      this.selectedCategory = 'All';
      this.searchQuery = '';
      this.onlyOutliers = false;
      this.daysBack = 15;
      this.sortBy = 'smart_signal';
      this.videoType = 'long';
      this.matchedChannels = [];
      this.loadFeed();
    },

    setVideoType(type) {
      if (this.videoType === type) return;
      this.videoType = type;
      this.loadFeed();
    },

    filterByCreator(name) {
      this.searchQuery = name;
      this.loadFeed();
    },

    async loadFeed() {
      this.loading = true;
      try {
        const params = new URLSearchParams({
          days_back: this.daysBack,
          sort_by: this.sortBy,
          limit: 50,
          video_type: this.videoType
        });

        if (this.selectedCategory && this.selectedCategory !== 'All') {
          params.append('category', this.selectedCategory);
        }
        if (this.searchQuery.trim()) {
          params.append('search', this.searchQuery.trim());
        }
        if (this.onlyOutliers) {
          params.append('min_multiplier', '1.8');
        }

        const res = await fetch(`/api/feed?${params.toString()}`);
        if (res.ok) {
          const data = await res.json();
          this.videos = data.videos || [];
          this.matchedChannels = data.matched_channels || [];
        }
      } catch (err) {
        console.error('Failed to load feed:', err);
      } finally {
        this.loading = false;
      }
    },

    async addCollabCreator(collab) {
      if (!collab || collab.is_tracked) return;
      const target = (collab.guest_handle || collab.guest_name || '').trim();
      if (!target) return;
      this.collabAdding = true;
      try {
        const res = await fetch('/api/channels', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url_or_handle: target })
        });
        if (res.ok) {
          collab.is_tracked = true;
          await this.loadChannels();
          await this.loadFeed();
        } else {
          const err = await res.json();
          alert(err.detail || 'Could not track channel. You can search manually.');
        }
      } catch (e) {
        alert('Network error adding collaborator.');
      } finally {
        this.collabAdding = false;
      }
    },

    async triggerCatalogDiscovery() {
      this.discoveryScanning = true;
      try {
        const res = await fetch('/api/discovery/scan', { method: 'POST' });
        if (res.ok) {
          alert('Aggressive creator catalog discovery started in background across Sections A, B & C.');
          setTimeout(async () => {
            await this.loadChannels();
            await this.loadFeed();
          }, 3500);
        }
      } catch (e) {
        console.error('Discovery scan error:', e);
      } finally {
        this.discoveryScanning = false;
      }
    },

    async loadChannels() {
      try {
        const res = await fetch('/api/channels');
        if (res.ok) {
          const data = await res.json();
          this.channels = data.channels || [];
        }
      } catch (err) {
        console.error('Failed to load channels:', err);
      }
    },

    async loadRawData() {
      try {
        const res = await fetch('/api/raw-channels');
        if (res.ok) {
          const data = await res.json();
          this.rawChannels = data.channels || [];
          this.rawStats = data.stats || {};
        }
      } catch (err) {
        console.error('Failed to load raw channels:', err);
      }
    },

    async triggerSync() {
      try {
        const res = await fetch('/api/sync', { method: 'POST' });
        if (res.ok || res.status === 409) {
          this.pollSync();
        }
      } catch (err) {
        console.error('Failed to trigger sync:', err);
      }
    },

    pollSync() {
      if (this.syncPollInterval) clearInterval(this.syncPollInterval);
      this.syncPollInterval = setInterval(async () => {
        await this.checkSyncStatus();
        if (!this.syncState.is_running) {
          clearInterval(this.syncPollInterval);
          this.syncPollInterval = null;
          this.loadFeed();
          this.loadChannels();
        }
      }, 1500);
    },

    async checkSyncStatus() {
      try {
        const res = await fetch('/api/sync/status');
        if (res.ok) {
          const data = await res.json();
          this.syncState = data.progress || { is_running: false };
          if (this.syncState.is_running && !this.syncPollInterval) {
            this.pollSync();
          }
        }
      } catch (err) {
        console.error('Failed to check sync status:', err);
      }
    },

    filteredChannels() {
      const q = (this.channelSearchQuery || '').trim().toLowerCase().replace(/^@/, '');
      if (!q) {
        return this.channels;
      }
      return this.channels.filter(ch => {
        const name = (ch.name || '').toLowerCase();
        const handle = (ch.handle || '').toLowerCase().replace(/^@/, '');
        const cat = (ch.category || '').toLowerCase();
        return name.includes(q) || handle.includes(q) || cat.includes(q);
      });
    },

    async addChannel(handleToAdd = null) {
      const target = (handleToAdd || this.channelSearchQuery || this.newChannelInput || '').trim();
      if (!target) return;
      this.addingChannel = true;
      try {
        const res = await fetch('/api/channels', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url_or_handle: target })
        });
        if (res.ok) {
          this.channelSearchQuery = '';
          this.newChannelInput = '';
          await this.loadChannels();
          await this.loadFeed();
        } else {
          const err = await res.json();
          alert(err.detail || 'Failed to add channel. Verify handle or URL.');
        }
      } catch (e) {
        alert('Network error adding channel.');
      } finally {
        this.addingChannel = false;
      }
    },

    async deleteChannel(channelId) {
      if (!confirm('Stop monitoring this creator?')) return;
      try {
        const res = await fetch(`/api/channels/${encodeURIComponent(channelId)}`, { method: 'DELETE' });
        if (res.ok) {
          await this.loadChannels();
          await this.loadFeed();
        }
      } catch (e) {
        console.error('Failed to delete channel:', e);
      }
    },

    openBlueprint(item) {
      this.activeBlueprint = item;
    },

    async reanalyze(videoId) {
      if (!videoId) return;
      try {
        const res = await fetch(`/api/outliers/${videoId}/analyze`, { method: 'POST' });
        if (res.ok) {
          const updated = await res.json();
          if (this.activeBlueprint && this.activeBlueprint.video_id === videoId) {
            this.activeBlueprint.summary_bullets = updated.summary_bullets;
            this.activeBlueprint.tools_mentioned = updated.tools_mentioned;
            this.activeBlueprint.viral_hook_angle = updated.viral_hook_angle;
          }
          await this.loadFeed();
        } else {
          alert('Re-analysis failed. Check Groq API configuration.');
        }
      } catch (e) {
        alert('Failed to reanalyze video.');
      }
    },

    formatNumber(num) {
      if (!num && num !== 0) return '0';
      if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
      if (num >= 1000) return (num / 1000).toFixed(0) + 'K';
      return Number(num).toLocaleString();
    },

    formatDuration(secs, isShort = false) {
      if (!secs || secs <= 0) {
        return isShort ? 'SHORTS' : '';
      }
      const h = Math.floor(secs / 3600);
      const m = Math.floor((secs % 3600) / 60);
      const s = Math.floor(secs % 60);
      if (h > 0) {
        return `${h}:${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
      }
      return `${m}:${s < 10 ? '0' : ''}${s}`;
    },

    formatRelativeTime(dateStr) {
      if (!dateStr) return 'Recently';
      try {
        const d = new Date(dateStr);
        const now = new Date();
        const diffMs = now - d;
        if (isNaN(diffMs) || diffMs < 0) return 'Just now';
        const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
        if (diffHours < 1) return 'Just now';
        if (diffHours === 1) return '1 hour ago';
        if (diffHours < 24) return `${diffHours} hours ago`;
        const diffDays = Math.floor(diffHours / 24);
        if (diffDays === 1) return '1 day ago';
        if (diffDays < 7) return `${diffDays} days ago`;
        const diffWeeks = Math.floor(diffDays / 7);
        if (diffWeeks === 1) return '1 week ago';
        if (diffWeeks < 4) return `${diffWeeks} weeks ago`;
        const diffMonths = Math.floor(diffDays / 30);
        if (diffMonths <= 1) return '1 month ago';
        return `${diffMonths} months ago`;
      } catch (e) {
        return 'Recently';
      }
    }
  };
}
