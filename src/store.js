// ============================================
// In-memory data store — mock MongoDB
// Pre-seeded with realistic fake data
// ============================================

const DOG_BREEDS = [
  'Golden Retriever', 'Husky', 'Corgi', 'Poodle', 'German Shepherd',
  'Labrador', 'Beagle', 'Shiba Inu', 'Dalmatian', 'Border Collie',
  'Samoyed', 'Pomeranian', 'Australian Shepherd', 'Akita', 'Chow Chow'
];

const USERNAMES = ['DogLover42', 'PawsAndClaws', 'WoofWoof', 'BarkKnight', 'FluffyFinder',
  'TailWagger', 'PupExplorer', 'HowlingMoon', 'SnoutSeeker', 'FurBuddy'];

const FORUM_TITLES = [
  'My dog twin is spot on! 🐕', 'Can\'t believe the resemblance!',
  'Tips for getting a better match', 'The algorithm is amazing!',
  'My whole family tried it', 'Show me your matches!',
  'Dogs that look like celebrities', 'Funniest match I\'ve seen',
  'How does the face matching work?', 'I look like a Corgi apparently 😂'
];

const FORUM_BODIES = [
  'Just uploaded my photo and got matched with a Golden Retriever. My friends say it\'s perfect — we both have that same goofy smile! Has anyone else gotten a surprisingly accurate match?',
  'I was skeptical at first, but the AI really nailed it. The eyes, the expression, even the way the hair falls — it\'s like looking at a furry mirror!',
  'Pro tip: use a photo with good lighting and a clear view of your face. Natural light works best. I tried different angles and got different breeds each time!',
  'The face-matching technology here is incredible. I\'m a CS student and I\'d love to know more about how CLIP embeddings work with the AFHQ dataset.',
  'We had a family game night where everyone uploaded their photos. My dad got matched with a Bulldog and we couldn\'t stop laughing. Best app ever!',
  'Drop your matches below! I want to see who got the most unusual breed. I got matched with a Chow Chow and honestly... I see it.',
  'Uploaded a photo of my favorite celebrity and got matched with an Akita. Honestly perfect. The regal energy is unmatched.',
  'My roommate and I both got matched with Huskies. We always knew we were kindred spirits! 😄',
  'Does anyone know if the matching considers things like hair color, face shape, or expression? I\'m curious about what features drive the similarity.',
  'The Corgi life chose me. Got matched three times and it\'s always a Corgi. I\'m embracing my inner loaf. 🍞🐾'
];

const COMMENT_BODIES = [
  'This is hilarious! I need to try this.', 'Great match! You two really do look alike.',
  'I got a similar result!', 'The resemblance is uncanny 😂', 'Love this app so much!',
  'Try uploading a side profile — you might get a different breed!',
  'Welcome to the Corgi club! 🐾', 'Haha this made my day!',
  'Can\'t wait to try it with my friends!', 'The AI is getting scary good at this.'
];

const DM_MESSAGES = [
  'Hey! Saw your match in the gallery, it\'s amazing!',
  'Thanks! I couldn\'t believe how accurate it was 😄',
  'Have you tried the multiplayer matching game? It\'s really fun',
  'Not yet! Wanna play together?',
  'Sure! I\'ll create a lobby, join in a sec',
  'Just uploaded a new photo, got matched with a different breed this time!',
  'Which breed did you get?',
  'A Samoyed! That fluffy white cloud dog 🐩',
  'Haha perfect, you do have that kind of energy!',
  'Thanks for the game, that was fun! Same time tomorrow?'
];

// Generate color for avatar placeholder
function hashColor(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = hash % 360;
  return `hsl(${Math.abs(hue)}, 65%, 50%)`;
}

// Generate SVG avatar
function generateAvatar(username) {
  const color = hashColor(username);
  const initial = username.charAt(0).toUpperCase();
  return `data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><rect width="200" height="200" fill="${color}"/><text x="100" y="120" text-anchor="middle" fill="white" font-size="80" font-family="sans-serif" font-weight="bold">${initial}</text></svg>`)}`;
}

// Generate dog placeholder image
function generateDogImage(breed, index) {
  const colors = ['#f59e0b', '#8b5cf6', '#ec4899', '#10b981', '#3b82f6', '#ef4444', '#6366f1', '#14b8a6', '#f97316', '#a855f7'];
  const color = colors[index % colors.length];
  return `data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400"><rect width="400" height="400" fill="${color}" rx="20"/><text x="200" y="170" text-anchor="middle" fill="white" font-size="80">🐕</text><text x="200" y="260" text-anchor="middle" fill="rgba(255,255,255,0.9)" font-size="24" font-family="sans-serif" font-weight="bold">${breed}</text></svg>`)}`;
}

// Generate human placeholder image
function generateHumanImage(username, index) {
  const colors = ['#374151', '#4b5563', '#1f2937', '#334155', '#3f3f46', '#44403c'];
  const color = colors[index % colors.length];
  return `data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400"><rect width="400" height="400" fill="${color}" rx="20"/><text x="200" y="170" text-anchor="middle" fill="white" font-size="80">👤</text><text x="200" y="260" text-anchor="middle" fill="rgba(255,255,255,0.7)" font-size="22" font-family="sans-serif">${username}</text></svg>`)}`;
}

function createId() {
  return Math.random().toString(36).substring(2, 12);
}

function randomDate(daysBack = 30) {
  const now = Date.now();
  return new Date(now - Math.random() * daysBack * 24 * 60 * 60 * 1000);
}

function randomInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

// =========== Build initial data ===========

// Users
const users = USERNAMES.map((username, i) => ({
  id: `user_${i}`,
  username,
  email: `${username.toLowerCase()}@example.com`,
  password: 'password123',
  avatar: generateAvatar(username),
  createdAt: randomDate(60),
}));

// Matches (shared + private)
const matches = [];
for (let i = 0; i < 20; i++) {
  const user = users[i % users.length];
  const breedIdx = i % DOG_BREEDS.length;
  matches.push({
    id: `match_${i}`,
    userId: user.id,
    username: user.username,
    humanImage: generateHumanImage(user.username, i),
    dogImage: generateDogImage(DOG_BREEDS[breedIdx], breedIdx),
    dogBreed: DOG_BREEDS[breedIdx],
    similarity: (70 + Math.random() * 28).toFixed(1),
    shared: i < 14, // first 14 are shared
    caption: i % 3 === 0 ? `My ${DOG_BREEDS[breedIdx]} twin!` : '',
    createdAt: randomDate(20),
  });
}

// Forum posts
const posts = FORUM_TITLES.map((title, i) => {
  const user = users[i % users.length];
  return {
    id: `post_${i}`,
    userId: user.id,
    username: user.username,
    avatar: user.avatar,
    title,
    body: FORUM_BODIES[i],
    mediaId: i % 3 === 0 ? matches[i % matches.length]?.dogImage : null,
    likes: randomInt(2, 45),
    dislikes: randomInt(0, 5),
    likedBy: [],
    dislikedBy: [],
    commentCount: 0, // will be calculated
    createdAt: randomDate(15),
  };
});

// Comments
const comments = [];
for (let i = 0; i < 30; i++) {
  const user = users[randomInt(0, users.length - 1)];
  const post = posts[randomInt(0, posts.length - 1)];
  comments.push({
    id: `comment_${i}`,
    postId: post.id,
    userId: user.id,
    username: user.username,
    avatar: user.avatar,
    body: COMMENT_BODIES[i % COMMENT_BODIES.length],
    mediaId: null,
    likes: randomInt(0, 15),
    dislikes: randomInt(0, 2),
    likedBy: [],
    dislikedBy: [],
    createdAt: new Date(post.createdAt.getTime() + randomInt(1, 48) * 60 * 60 * 1000),
  });
}

// Update post comment counts
posts.forEach(p => {
  p.commentCount = comments.filter(c => c.postId === p.id).length;
});

// Conversations + Messages
const conversations = [
  {
    id: 'conv_0',
    participants: ['user_0', 'user_1'],
    lastMessage: DM_MESSAGES[1],
    lastMessageAt: randomDate(1),
    unreadCount: { user_0: 0, user_1: 1 },
  },
  {
    id: 'conv_1',
    participants: ['user_0', 'user_2'],
    lastMessage: DM_MESSAGES[5],
    lastMessageAt: randomDate(2),
    unreadCount: { user_0: 2, user_1: 0 },
  },
  {
    id: 'conv_2',
    participants: ['user_0', 'user_3'],
    lastMessage: DM_MESSAGES[9],
    lastMessageAt: randomDate(3),
    unreadCount: { user_0: 0, user_3: 0 },
  },
];

const messagesList = [];
conversations.forEach(conv => {
  const [u1, u2] = conv.participants;
  for (let i = 0; i < 10; i++) {
    const senderId = i % 2 === 0 ? u1 : u2;
    const sender = users.find(u => u.id === senderId);
    messagesList.push({
      id: `msg_${conv.id}_${i}`,
      conversationId: conv.id,
      senderId,
      senderUsername: sender?.username || 'Unknown',
      body: DM_MESSAGES[i % DM_MESSAGES.length],
      mediaId: null,
      createdAt: new Date(Date.now() - (10 - i) * 15 * 60 * 1000),
    });
  }
});

// Notifications
const notifications = [
  { id: 'notif_0', userId: 'user_0', type: 'match_ready', message: 'Your dog match is ready!', targetId: 'match_0', read: false, createdAt: randomDate(0.1) },
  { id: 'notif_1', userId: 'user_0', type: 'dm_received', message: 'PawsAndClaws sent you a message', targetId: 'conv_0', read: false, createdAt: randomDate(0.2) },
  { id: 'notif_2', userId: 'user_0', type: 'post_reaction', message: 'WoofWoof liked your post', targetId: 'post_0', read: true, createdAt: randomDate(0.5) },
  { id: 'notif_3', userId: 'user_0', type: 'match_ready', message: 'Another match completed!', targetId: 'match_1', read: true, createdAt: randomDate(1) },
];

// Lobbies
const lobbies = [
  { id: 'lobby_0', name: 'Paw Patrol Squad', hostId: 'user_1', hostUsername: 'PawsAndClaws', players: ['user_1', 'user_2'], maxPlayers: 4, status: 'waiting', createdAt: randomDate(0.1) },
  { id: 'lobby_1', name: 'Bark After Dark', hostId: 'user_3', hostUsername: 'BarkKnight', players: ['user_3'], maxPlayers: 4, status: 'waiting', createdAt: randomDate(0.2) },
];

// Jobs (processing queue)
const jobs = [];


// =========== Store API ===========

export const store = {
  // --- Users ---
  getUser(id) { return users.find(u => u.id === id); },
  getUserByUsername(username) { return users.find(u => u.username === username || u.email === username); },
  createUser({ username, email, password }) {
    if (users.find(u => u.username === username)) return { error: 'Username already taken' };
    if (users.find(u => u.email === email)) return { error: 'Email already registered' };
    const user = { id: `user_${createId()}`, username, email, password, avatar: generateAvatar(username), createdAt: new Date() };
    users.push(user);
    return { user };
  },

  // --- Matches ---
  getMatch(id) { return matches.find(m => m.id === id); },
  getMatchesByUser(userId) { return matches.filter(m => m.userId === userId).sort((a, b) => b.createdAt - a.createdAt); },
  getSharedMatches(page = 1, limit = 12) {
    const shared = matches.filter(m => m.shared).sort((a, b) => b.createdAt - a.createdAt);
    return { items: shared.slice((page - 1) * limit, page * limit), total: shared.length };
  },
  getFeaturedMatches(limit = 6) {
    return matches.filter(m => m.shared).slice(0, limit);
  },
  createMatch({ userId, username, humanImage }) {
    const breedIdx = Math.floor(Math.random() * DOG_BREEDS.length);
    const m = {
      id: `match_${createId()}`,
      userId, username,
      humanImage,
      dogImage: generateDogImage(DOG_BREEDS[breedIdx], breedIdx),
      dogBreed: DOG_BREEDS[breedIdx],
      similarity: (70 + Math.random() * 28).toFixed(1),
      shared: false,
      caption: '',
      createdAt: new Date(),
    };
    matches.unshift(m);
    return m;
  },
  toggleShare(matchId) {
    const m = matches.find(m => m.id === matchId);
    if (m) m.shared = !m.shared;
    return m;
  },
  deleteMatch(matchId) {
    const idx = matches.findIndex(m => m.id === matchId);
    if (idx > -1) matches.splice(idx, 1);
  },

  // --- Jobs (queue) ---
  getJobsByUser(userId) { return jobs.filter(j => j.userId === userId); },
  createJob({ userId, username, humanImage, urgent, fileSize }) {
    const job = {
      id: `job_${createId()}`,
      userId, username, humanImage,
      urgent: !!urgent,
      fileSize: fileSize || 0,
      status: 'queued', // queued | processing | done
      progress: 0,
      matchId: null,
      createdAt: new Date(),
    };
    jobs.push(job);
    return job;
  },
  updateJob(jobId, updates) {
    const j = jobs.find(j => j.id === jobId);
    if (j) Object.assign(j, updates);
    return j;
  },

  // --- Posts ---
  getPosts(page = 1, limit = 10) {
    const sorted = [...posts].sort((a, b) => b.createdAt - a.createdAt);
    return { items: sorted.slice((page - 1) * limit, page * limit), total: posts.length };
  },
  searchPosts(query) {
    const q = query.toLowerCase();
    return posts.filter(p =>
      p.title.toLowerCase().includes(q) ||
      p.body.toLowerCase().includes(q)
    );
  },
  getPost(id) { return posts.find(p => p.id === id); },
  createPost({ userId, username, avatar, title, body, mediaId }) {
    const post = {
      id: `post_${createId()}`, userId, username, avatar, title, body, mediaId,
      likes: 0, dislikes: 0, likedBy: [], dislikedBy: [],
      commentCount: 0, createdAt: new Date()
    };
    posts.unshift(post);
    return post;
  },
  reactToPost(postId, userId, type) {
    const p = posts.find(p => p.id === postId);
    if (!p) return null;
    if (type === 'like') {
      if (p.likedBy.includes(userId)) { p.likedBy = p.likedBy.filter(id => id !== userId); p.likes--; }
      else { p.likedBy.push(userId); p.likes++; p.dislikedBy = p.dislikedBy.filter(id => id !== userId); p.dislikes = Math.max(0, p.dislikedBy.length); }
    } else {
      if (p.dislikedBy.includes(userId)) { p.dislikedBy = p.dislikedBy.filter(id => id !== userId); p.dislikes--; }
      else { p.dislikedBy.push(userId); p.dislikes++; p.likedBy = p.likedBy.filter(id => id !== userId); p.likes = Math.max(0, p.likedBy.length); }
    }
    return p;
  },

  // --- Comments ---
  getCommentsByPost(postId) { return comments.filter(c => c.postId === postId).sort((a, b) => a.createdAt - b.createdAt); },
  createComment({ postId, userId, username, avatar, body, mediaId }) {
    const c = {
      id: `comment_${createId()}`, postId, userId, username, avatar, body, mediaId,
      likes: 0, dislikes: 0, likedBy: [], dislikedBy: [], createdAt: new Date()
    };
    comments.push(c);
    const post = posts.find(p => p.id === postId);
    if (post) post.commentCount++;
    return c;
  },
  reactToComment(commentId, userId, type) {
    const c = comments.find(c => c.id === commentId);
    if (!c) return null;
    if (type === 'like') {
      if (c.likedBy.includes(userId)) { c.likedBy = c.likedBy.filter(id => id !== userId); c.likes--; }
      else { c.likedBy.push(userId); c.likes++; c.dislikedBy = c.dislikedBy.filter(id => id !== userId); c.dislikes = Math.max(0, c.dislikedBy.length); }
    } else {
      if (c.dislikedBy.includes(userId)) { c.dislikedBy = c.dislikedBy.filter(id => id !== userId); c.dislikes--; }
      else { c.dislikedBy.push(userId); c.dislikes++; c.likedBy = c.likedBy.filter(id => id !== userId); c.likes = Math.max(0, c.likedBy.length); }
    }
    return c;
  },

  // --- Conversations / DMs ---
  getConversationsByUser(userId) {
    return conversations.filter(c => c.participants.includes(userId)).sort((a, b) => b.lastMessageAt - a.lastMessageAt);
  },
  getConversation(id) { return conversations.find(c => c.id === id); },
  getMessages(conversationId) { return messagesList.filter(m => m.conversationId === conversationId).sort((a, b) => a.createdAt - b.createdAt); },
  sendMessage({ conversationId, senderId, senderUsername, body, mediaId }) {
    const msg = {
      id: `msg_${createId()}`, conversationId, senderId, senderUsername, body, mediaId, createdAt: new Date()
    };
    messagesList.push(msg);
    const conv = conversations.find(c => c.id === conversationId);
    if (conv) {
      conv.lastMessage = body;
      conv.lastMessageAt = new Date();
      conv.participants.forEach(p => { if (p !== senderId) conv.unreadCount[p] = (conv.unreadCount[p] || 0) + 1; });
    }
    return msg;
  },
  createConversation(userId, recipientId) {
    const existing = conversations.find(c => c.participants.includes(userId) && c.participants.includes(recipientId));
    if (existing) return existing;
    const conv = {
      id: `conv_${createId()}`,
      participants: [userId, recipientId],
      lastMessage: '',
      lastMessageAt: new Date(),
      unreadCount: {},
    };
    conversations.push(conv);
    return conv;
  },
  markConversationRead(conversationId, userId) {
    const conv = conversations.find(c => c.id === conversationId);
    if (conv) conv.unreadCount[userId] = 0;
  },
  getAllUsers() { return users; },

  // --- Notifications ---
  getNotifications(userId) { return notifications.filter(n => n.userId === userId).sort((a, b) => b.createdAt - a.createdAt); },
  getUnreadCount(userId) { return notifications.filter(n => n.userId === userId && !n.read).length; },
  markAllRead(userId) { notifications.filter(n => n.userId === userId).forEach(n => n.read = true); },
  addNotification({ userId, type, message, targetId }) {
    const n = { id: `notif_${createId()}`, userId, type, message, targetId, read: false, createdAt: new Date() };
    notifications.unshift(n);
    return n;
  },

  // --- Lobbies ---
  getLobbies() { return lobbies.filter(l => l.status === 'waiting'); },
  getLobby(id) { return lobbies.find(l => l.id === id); },
  createLobby({ name, hostId, hostUsername }) {
    const lobby = {
      id: `lobby_${createId()}`, name, hostId, hostUsername,
      players: [hostId], maxPlayers: 4, status: 'waiting', createdAt: new Date()
    };
    lobbies.push(lobby);
    return lobby;
  },
  joinLobby(lobbyId, userId) {
    const l = lobbies.find(l => l.id === lobbyId);
    if (!l || l.players.length >= l.maxPlayers) return null;
    if (!l.players.includes(userId)) l.players.push(userId);
    return l;
  },
  leaveLobby(lobbyId, userId) {
    const l = lobbies.find(l => l.id === lobbyId);
    if (l) l.players = l.players.filter(p => p !== userId);
    if (l && l.players.length === 0) l.status = 'closed';
    return l;
  },

  // --- Game ---
  generateRound(count = 4) {
    const shared = matches.filter(m => m.shared);
    const shuffled = [...shared].sort(() => Math.random() - 0.5).slice(0, count);
    const humans = shuffled.map(m => ({ id: m.id, image: m.humanImage, username: m.username }));
    const dogs = shuffled.map(m => ({ id: m.id, image: m.dogImage, breed: m.dogBreed })).sort(() => Math.random() - 0.5);
    const answer = {};
    shuffled.forEach(m => { answer[m.id] = m.id; });
    const token = createId();
    // Store answer in memory
    if (!store._gameAnswers) store._gameAnswers = {};
    store._gameAnswers[token] = answer;
    return { token, humans, dogs };
  },
  checkAnswer(token, pairs) {
    const answer = store._gameAnswers?.[token];
    if (!answer) return { error: 'Invalid round' };
    let correct = 0;
    const results = {};
    Object.entries(pairs).forEach(([humanId, dogId]) => {
      const isCorrect = humanId === dogId;
      results[humanId] = { correct: isCorrect, correctDogId: humanId };
      if (isCorrect) correct++;
    });
    return { correct, total: Object.keys(answer).length, results };
  },

  // --- Forum stats for dashboard ---
  getForumStats(userId) {
    const userPosts = posts.filter(p => p.userId === userId);
    const totalLikes = userPosts.reduce((sum, p) => sum + p.likes, 0);
    const totalDislikes = userPosts.reduce((sum, p) => sum + p.dislikes, 0);
    return { postCount: userPosts.length, totalLikes, totalDislikes, posts: userPosts };
  },
};

export default store;
