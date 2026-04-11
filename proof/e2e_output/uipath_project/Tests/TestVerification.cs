using System;
using UiPath.CodedWorkflows;
using UiPath.UIAutomationNext.API;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace TheInternetAutomation
{
    public class SelectorVerification : CodedWorkflow
    {
        [TestCase]
        public void VerifyAllSelectors()
        {
            Log("Starting selector verification test", LogLevel.Info);
            
            // Verify all harvested selectors resolve
            Assert.IsNotNull(uiAutomation.Find("S001_Add_Element_0"), "Selector S001_Add_Element_0 not found");
            Assert.IsNotNull(uiAutomation.Find("S002_checkbox_1_0"), "Selector S002_checkbox_1_0 not found");
            Assert.IsNotNull(uiAutomation.Find("S002_checkbox_2_1"), "Selector S002_checkbox_2_1 not found");
            Assert.IsNotNull(uiAutomation.Find("S003_Dropdown_0"), "Selector S003_Dropdown_0 not found");
            Assert.IsNotNull(uiAutomation.Find("S004_Number_Input_0"), "Selector S004_Number_Input_0 not found");
            Assert.IsNotNull(uiAutomation.Find("S005_Input_Field_0"), "Selector S005_Input_Field_0 not found");
            Assert.IsNotNull(uiAutomation.Find("S005_Result_1"), "Selector S005_Result_1 not found");
            
            Log("All selectors verified successfully", LogLevel.Info);
        }
    }
}