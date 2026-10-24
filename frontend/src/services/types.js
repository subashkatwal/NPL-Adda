/**
 * Shared JSDoc types mirroring the Django API (see /api/docs). Import with
 * `@typedef {import("./types.js").Team} Team` in other modules.
 *
 * @typedef {{ id: string, name: string, short_name: string, city: string, primary_color: string,
 *   secondary_color: string, asset_url: string, is_active: boolean }} Team
 * @typedef {{ id: string, nickname: string, fan_personality: string, bio: string, card_theme: string,
 *   is_public: boolean, current_team: Team | null, is_owner: boolean, created_at: string }} FanProfile
 * @typedef {{ id: string, text: string, display_order: number }} PollOption
 * @typedef {{ poll: string, total_votes: number, options: {id: string, text: string, votes: number}[] }} PollResults
 * @typedef {{ id: string, question: string, description: string, team: string | null, match: string | null,
 *   opens_at: string, closes_at: string, status: string, results_visibility: "always" | "after_vote" | "after_close",
 *   options: PollOption[], is_accepting_votes: boolean, my_vote: string | null, results: PollResults | null }} Poll
 * @typedef {{ id: string, match: string, predicted_winner: string, submitted_at: string, points_awarded: number,
 *   scored_at: string | null }} Prediction
 * @typedef {{ rank: number, team: Team, points: number, members: number, activity_count: number }} TeamRank
 * @typedef {{ id: string, rank: number, nickname: string, fan_personality: string, points: number }} FanRank
 * @typedef {{ badge: {id: string, code: string, name: string, description: string, icon_name: string, rule_key: string},
 *   current: number, target: number, completed: boolean, awarded_at: string | null }} Challenge
 * @typedef {{ season: {id: string, name: string, year: number} | null, points: number, rank: number | null,
 *   votes: number, predictions_made: number, predictions_correct: number, predictions_pending: number,
 *   badges_earned: number, posts_published: number, teams_supported: number }} SeasonSummary
 * @typedef {{ id: string, activity_type: string, points_delta: number, occurred_at: string, team: string | null }} Activity
 * @typedef {{ caption: string, team: string | null, template: {slug: string, category: string,
 *   layout_config: object} | null }} PostMeme
 * @typedef {{ id: string, author_nickname: string, team: string | null, content_type: string, title: string,
 *   body: string, language: string, status: string, score: number, meme: PostMeme | null, published_at: string | null,
 *   created_at: string }} Post
 * @typedef {{ id: string, name: string, slug: string, category: string, layout_config: object }} MemeTemplate
 * @typedef {{ id: string, caption: string, alternate_captions: string[], source_references: object[],
 *   template: string | null, team: string | null, match: string | null, status: string, published_post: string | null }} MemeDraft
 * @typedef {{ request: {id: string, status: string, provider: string, model_name: string},
 *   draft: MemeDraft, captions: string[], is_mock: boolean, notice: string | null }} GenerationResult
 * @typedef {{ count: number, next: string | null, previous: string | null, results: any[] }} Page
 */
export {};
