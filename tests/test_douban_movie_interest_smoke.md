# Manual Douban Movie interest smoke test

Run only with your own authenticated `DOUBAN_COOKIE` and a movie subject you explicitly intend to mark 想看.

The provider-level verification target is:

1. `DoubanMovieSearchClient` resolves a `movie.douban.com/subject/<id>/` candidate.
2. `DoubanMovieInterestClient.check_auth(probe_subject_id=<id>)` succeeds without changing state.
3. `mark_want_to_watch(<id>, confirmed=True)` writes `wish` on the Movie host.
4. The client immediately reads the Movie interest endpoint again and returns `verified=True`, `actual_status="wish"`.

Do not use this checklist to bypass captcha or anti-abuse responses. If Douban blocks or redirects to login, refresh the normal browser session and stop automated writes until auth is healthy.
