struct qm_cli_command { const char *name,*help; void (*function)(char *,int,int,char **); };
int qm_cli_register_command(const struct qm_cli_command *command);
