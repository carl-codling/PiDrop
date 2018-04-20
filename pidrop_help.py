#!/usr/bin/python


help_questions = {"name":'CATEGORIES:',"children":[
	{
		"name": 'Configuration Questions', "children":[

	# Question Start --------------------
	# ===================================

			{"name":'How do I set the PiDrop Directory?',"children":[
				{"answer":
"""
1) From the welcome screen select 'Configure PiDrop'
2) Select 'Set the locations for your PiDrop Directories'
3) Change 'PiDrop Root Directory' to the appropriate path
4) Click 'Save and Exit'
"""
				}
			]},

	#######################################

	# Question Start --------------------
	# ===================================

			{"name":'How do I set the Import/Export Directories?',"children":[
				{"answer":
"""
1) From the welcome screen select 'Configure PiDrop'
2) Select 'Set the locations for your PiDrop Directories'
3) Change the directories to the appropriate paths
4) Click 'Save and Exit'
"""
				}
			]},

	#######################################

	#######################################

	# Question Start --------------------
	# ===================================

			{"name":'How do I change my API key?',"children":[
				{"answer":
"""
1) From a terminal enter 
    sudo python ~/PiDrop/pidrop.py cfg
2) Type 'set-token' and hit [enter]
3) Enter your token and again hit [enter]
4) Type 'save' and hit [enter]
5) Type 'exit' and hit [enter]
"""
				}
			]},

	#######################################


		]
	},
	{
		"name": 'Managing files and folders in the directory browser', "children":[
			{"name":'How do I move a file?',"children":[
				{"answer":
"""
1) Select 1 or more files using the [s] key
"""
				}
			]}
		]
	}
]}