# OAuth status

OAuth is not implemented. Canvas administrators must first register and enable a developer key for this application. A student's approved-integrations list shows existing authorisations; it is not client registration.

For a future read-only integration, request these scopes from your institution:

- `url:GET|/api/v1/courses`
- `url:GET|/api/v1/users/self/course_nicknames`
- `url:GET|/api/v1/courses/:course_id/assignment_groups`
- `url:GET|/api/v1/courses/:course_id/assignments`

Course requests include terms and total scores; assignments include the student's submission. Confirm supported native-app authorisation and redirect options before implementing browser callbacks, credential storage and refresh. Never distribute a confidential client secret in a desktop package.

Until then, use a personal token, an explicitly supplied session cookie, or browser snapshot sync. Institutional settings may restrict these methods too.

References: [Canvas OAuth](https://developerdocs.instructure.com/services/canvas/oauth2/file.oauth), [developer keys and scopes](https://developerdocs.instructure.com/services/canvas/oauth2/file.developer_keys).
