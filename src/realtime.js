// ============================================
// Simulated real-time (Socket.IO replacement)
// Event emitter + fake processing/notifications
// ============================================

const listeners = {};

export const realtime = {
  on(event, callback) {
    if (!listeners[event]) listeners[event] = [];
    listeners[event].push(callback);
  },

  off(event, callback) {
    if (!listeners[event]) return;
    listeners[event] = listeners[event].filter(cb => cb !== callback);
  },

  emit(event, data) {
    if (!listeners[event]) return;
    listeners[event].forEach(cb => cb(data));
  },

  // Simulate job processing with progress updates
  simulateJobProcessing(job, store, auth) {
    let progress = 0;
    const interval = setInterval(() => {
      progress += Math.random() * 20 + 10;
      if (progress >= 100) {
        progress = 100;
        clearInterval(interval);

        // Create the match
        const match = store.createMatch({
          userId: job.userId,
          username: job.username,
          humanImage: job.humanImage,
        });

        store.updateJob(job.id, { status: 'done', progress: 100, matchId: match.id });

        // Emit events
        realtime.emit('match_ready', { jobId: job.id, matchId: match.id, match });
        realtime.emit('queue_update', { jobId: job.id, status: 'done', progress: 100 });

        // Add notification
        const currentUser = auth.getCurrentUser();
        if (currentUser && currentUser.id === job.userId) {
          const notif = store.addNotification({
            userId: job.userId,
            type: 'match_ready',
            message: `Your ${match.dogBreed} match is ready!`,
            targetId: match.id,
          });
          realtime.emit('notification', notif);
        }
      } else {
        store.updateJob(job.id, { status: 'processing', progress: Math.min(progress, 95) });
        realtime.emit('queue_update', { jobId: job.id, status: 'processing', progress: Math.min(progress, 95) });
      }
    }, job.urgent ? 400 : 800);

    return interval;
  },

  // Simulate incoming DM (for demo)
  simulateIncomingDM(conversationId, store) {
    const conv = store.getConversation(conversationId);
    if (!conv) return;

    const botReplies = [
      'That\'s awesome! 🐕',
      'Haha, I love that!',
      'You should try uploading another photo!',
      'My match was a Husky, perfect for me!',
      'Let\'s play the matching game later!',
      'Have you seen the gallery lately? Some great matches there.',
    ];

    setTimeout(() => {
      const otherUserId = conv.participants.find(p => p !== store._currentViewUserId);
      if (!otherUserId) return;
      const otherUser = store.getUser(otherUserId);
      if (!otherUser) return;

      const msg = store.sendMessage({
        conversationId,
        senderId: otherUserId,
        senderUsername: otherUser.username,
        body: botReplies[Math.floor(Math.random() * botReplies.length)],
      });

      realtime.emit('dm_received', { conversationId, message: msg });
    }, 2000 + Math.random() * 3000);
  },
};

export default realtime;
