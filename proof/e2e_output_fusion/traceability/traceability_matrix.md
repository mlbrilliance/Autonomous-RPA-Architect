# Traceability Matrix: PDD → IR → XAML → Object Repository → Config

**Total entries**: 23  
**Complete**: 22  
**Partial**: 1


## Full Matrix

| PDD Section | PDD Requirement | IR Node | XAML File | XAML Element | Obj Repo | Config | Status |
|-------------|-----------------|---------|-----------|-------------|----------|--------|--------|
| Process Overview | Name: WebInteractionAutomation | process_name | Main.xaml | StateMachine DisplayName='WebInteraction... | - | logF_BusinessProcessName | COMPLETE |
| Process Overview | Type: transactional | process_type | Framework/GetTransactionData.xaml | Queue-based Transaction Retrieval (trans... | - | - | COMPLETE |
| Systems | TheInternet (web) — https://the-internet.herokuapp... | systems[].name='TheInternet' | Framework/InitAllApplications.xaml | Open TheInternet (web) | .objects/TheInternet/1.0/TheIn | - | COMPLETE |
| Actions/S001 | click 'Add Element' | transactions['InteractWithTest | Framework/Process.xaml | ui:NClick DisplayName='Click Add Element... | .objects/TheInternet/1.0/TheIn | - | COMPLETE |
| Actions/S002 | check 'checkbox 1' | transactions['InteractWithTest | Framework/Process.xaml | ui:NCheck DisplayName='Check checkbox 1' | .objects/TheInternet/1.0/TheIn | - | COMPLETE |
| Actions/S002 | check 'checkbox 2' | transactions['InteractWithTest | Framework/Process.xaml | ui:NCheck DisplayName='Check checkbox 2' | .objects/TheInternet/1.0/TheIn | - | COMPLETE |
| Actions/S003 | select_item 'Dropdown' = 'Option 1' | transactions['InteractWithTest | Framework/Process.xaml | ui:NSelectItem DisplayName='Select_Item ... | .objects/TheInternet/1.0/TheIn | - | COMPLETE |
| Actions/S004 | type_into 'Number Input' = '42' | transactions['InteractWithTest | Framework/Process.xaml | ui:NTypeInto DisplayName='Type_Into Numb... | .objects/TheInternet/1.0/TheIn | - | COMPLETE |
| Actions/S005 | type_into 'Input Field' = 'Hello World' | transactions['InteractWithTest | Framework/Process.xaml | ui:NTypeInto DisplayName='Type_Into Inpu... | .objects/TheInternet/1.0/TheIn | - | COMPLETE |
| Actions/S005 | get_text 'Result' | transactions['InteractWithTest | Framework/Process.xaml | ui:NGetText (placeholder) | .objects/TheInternet/1.0/TheIn | - | PARTIAL (placeholder selector) |
| Configuration | MaxRetryNumber = 3 | config['MaxRetryNumber'] | Main.xaml (MaxRetryNumber variable) | Config("MaxRetryNumber") accessor | - | MaxRetryNumber | COMPLETE |
| Configuration | LogLevel = Info | config['LogLevel'] | All XAML files (LogMessage Level) | Config("LogLevel") accessor | - | LogLevel | COMPLETE |
| Configuration | OrchestratorQueueName = WebInteraction_Queue | config['OrchestratorQueueName' | Framework/GetTransactionData.xaml (QueueName) | Config("OrchestratorQueueName") accessor | - | OrchestratorQueueName | COMPLETE |
| Configuration | MaxConsecutiveSystemExceptions = 3 | config['MaxConsecutiveSystemEx | Data/Config.xlsx | Config("MaxConsecutiveSystemExceptions")... | - | MaxConsecutiveSystemExceptions | COMPLETE |
| REFramework Structure | REFramework requires Main.xaml | process_type='transactional' → | Main.xaml | State machine entry point with Init/GetT... | - | - | COMPLETE |
| REFramework Structure | REFramework requires Framework/InitAllSettings.xam... | process_type='transactional' → | Framework/InitAllSettings.xaml | Reads Config.xlsx into Config dictionary | - | - | COMPLETE |
| REFramework Structure | REFramework requires Framework/InitAllApplications... | process_type='transactional' → | Framework/InitAllApplications.xaml | Opens and logs into target applications | - | - | COMPLETE |
| REFramework Structure | REFramework requires Framework/GetTransactionData.... | process_type='transactional' → | Framework/GetTransactionData.xaml | Retrieves queue item from Orchestrator | - | - | COMPLETE |
| REFramework Structure | REFramework requires Framework/Process.xaml | process_type='transactional' → | Framework/Process.xaml | Executes transaction processing with UI ... | - | - | COMPLETE |
| REFramework Structure | REFramework requires Framework/SetTransactionStatu... | process_type='transactional' → | Framework/SetTransactionStatus.xaml | Sets queue item status (Success/Failed/R... | - | - | COMPLETE |
| REFramework Structure | REFramework requires Framework/EndProcess.xaml | process_type='transactional' → | Framework/EndProcess.xaml | Cleanup and final logging | - | - | COMPLETE |
| REFramework Structure | REFramework requires Framework/CloseAllApplication... | process_type='transactional' → | Framework/CloseAllApplications.xaml | Gracefully closes target applications | - | - | COMPLETE |
| REFramework Structure | REFramework requires Framework/KillAllProcesses.xa... | process_type='transactional' → | Framework/KillAllProcesses.xaml | Force-kills application processes | - | - | COMPLETE |
