using System;
using UiPath.CodedWorkflows;
using UiPath.UIAutomationNext.API;

namespace TheInternetAutomation
{
    public class ProcessTestPages : CodedWorkflow
    {
        [Workflow]
        public void Execute()
        {
            Log("Starting TheInternet automation", LogLevel.Info);
            using var screen = uiAutomation.Open(Descriptors.TheInternet.TheInternet);
            
            screen.Click("S001_Add_Element_0");
            Log("Done: Add Element", LogLevel.Info);
            screen.Click("S002_checkbox_1_0");
            Log("Done: checkbox 1", LogLevel.Info);
            screen.Click("S002_checkbox_2_1");
            Log("Done: checkbox 2", LogLevel.Info);
            screen.Click("S003_Dropdown_0");
            Log("Done: Dropdown", LogLevel.Info);
            screen.TypeInto("S004_Number_Input_0", "42");
            Log("Done: Number Input", LogLevel.Info);
            screen.TypeInto("S005_Input_Field_0", "Hello World");
            Log("Done: Input Field", LogLevel.Info);
        }
    }
}