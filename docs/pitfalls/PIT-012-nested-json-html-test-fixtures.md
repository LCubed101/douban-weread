# PIT-012 — Hand-written JSON with embedded HTML can make tests fail before parser logic runs

## Symptom

The authenticated-interest test suite reached 51 tests, but two tests failed with:

```text
json.decoder.JSONDecodeError: Expecting ',' delimiter
DoubanProviderError: Douban interest lookup response was not valid JSON.
```

The failing tests were intended to validate parsing of an HTML fragment embedded inside a JSON response, for example an `<input name="interest" ...>` element.

## Diagnosis

The production parser had not yet been reached. Failure occurred in `json.loads()` while decoding the mocked response body.

This distinguished a **test fixture construction bug** from a provider/parser bug.

## Root cause

The tests hand-wrote JSON strings that themselves contained HTML attributes with double quotes. This creates two nested escaping layers:

```text
Python string
  -> JSON string
     -> embedded HTML attributes
```

A quoting mistake at the outer layers can produce invalid JSON even though the intended HTML is valid.

## Resolution

Construct JSON fixture bodies with Python's JSON encoder instead of hand-writing escaped JSON:

```python
payload = json.dumps({
    "html": '<input type="radio" name="interest" value="do" checked>'
})
```

The same rule is now used for other JSON test responses in `test_douban_interest.py`.

## Prevention / test rule

When mock responses contain nested structured content:

- use `json.dumps()` for JSON;
- do not manually maintain JSON escape sequences around embedded HTML;
- keep fake cookies and tokens obviously synthetic;
- when a parser test fails, first identify whether failure happens in transport decoding, JSON decoding, HTML parsing, or business-state interpretation.

## General lesson

**A fixture should fail only when the behavior under test is wrong.** If a fixture itself cannot be decoded, it is testing string escaping rather than provider behavior.