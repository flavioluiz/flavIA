# Use cases

## Academic research

Organize your papers in a folder and let flavIA create a specialized assistant for the topic:

```bash
cd ~/research/cognitive-science
flavia --init
flavia
> Compare the working memory models discussed in the papers
> What are the main criticisms of Baddeley's model?
```

The wizard analyzes the PDF content and creates adapted agents -- for example, a cognitive science main agent with sub-agents for summarization, concept explanation, and citation search.

## Course materials

Use flavIA as a tutor for a course:

```bash
cd ~/courses/organic-chemistry
flavia --init
flavia
> Explain the SN2 mechanism with examples
> What is the difference between SN1 and SN2?
```

## Legal documents

```bash
cd ~/cases/contract-dispute
flavia --init
flavia
> Which clauses deal with early termination?
> Summarize each party's obligations
```

## Book analysis

```bash
cd ~/books/philosophy
flavia --init
flavia
> Compare Kant's and Hume's views on causality
> Summarize the main argument of Chapter 3
```

## Source code

flavIA is not limited to PDFs. Initialize in a software project folder:

```bash
cd ~/projects/my-app
flavia --init
flavia
> Explain the overall architecture of the project
> How does the authentication system work?
> Suggest improvements to the module organization
```

## Remote access via Telegram

Any of the scenarios above can be accessed from anywhere via Telegram:

```bash
cd ~/research/my-topic
flavia --init              # set up agents
flavia --setup-telegram    # configure bot
flavia --telegram          # start the bot
```

Then just chat with the bot on Telegram from your phone or computer.

## Multiple projects

Each folder can have its own configuration. Just run `flavia --init` in each one:

```bash
~/research/topic-A/.flavia/    # agents for topic A
~/research/topic-B/.flavia/    # agents for topic B
~/courses/my-course/.flavia/   # agents for the course
```

To share provider configurations across projects, use `~/.config/flavia/`:

```bash
~/.config/flavia/providers.yaml   # shared providers
~/.config/flavia/.env             # shared API keys
```

Local configurations (`.flavia/`) always take priority over user-level ones (`~/.config/flavia/`).
