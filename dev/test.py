#test File for lookup.py

from lookup import translate_word, print_translation, servo_lut

#get summary data (pass/fail state) from word/character input
def run_braille_test(word):
    error_flag = False
    results = []

    print("=" * 60)
    print(f"Testing: '{word}'")
    results = translate_word(word, servo_lut)
    print_translation(results)
    print("")

    invalid_letters = []
    motor_overflow = False

    for item in results:
        character = item[0] #letter/character
        motors = item[1] #list of motor positions
        if not motors:# if motors list is empty
            if character.isalpha():
                motor_overflow = True
            elif character.strip(): #ignore spaces
                invalid_letters.append(character)

    #flag error if any issues exist
    if invalid_letters:
        error_flag = True
    if motor_overflow:
        error_flag = True

    return {
        "word": word,
        "results": results,
        "error_flag": error_flag,
        "invalid_letters": invalid_letters,
        "motor_overflow": motor_overflow
    }

def main():

    test_cases = [
        "A", 
        "AB", 
        "abd",
        "Z",
        "YZ",
        "ZY",
        "abcdefgh",
        "HELLO", 
        "H ELLO",
        "bRaIlLe",
        "BHAV",
        "1", #should fail - need to implement numbers
        "TEST123", #should fail
        "LONGWORDXYZ", #should fail - exceeds 8 characters
        "WWWWWWWW", #boundary - should pass
        "WWWWWWWWW", #boundary - should fail
        " ", #should pass
        ".", #should fail - no special characters
        ",", #should fail
        "!@#", #should fail
        "ABCDEFGH!",
        "ABCDEFGHI"
    ]

    print("\nTest Begins:\n")
    all_summaries = []

    #acquire data for each test case
    for word in test_cases:
        summary = run_braille_test(word)
        all_summaries.append(summary)

    #create summary table
    print("\nSummary:\n")
    print(f"{'Word':<15} {'Active Motors':<35} {'Status':<13} {'Reason'}")

    #iterate through each test entry and summarize results
    for entry in all_summaries:
        word = entry["word"]
        results = entry["results"]

        #get active motor counts
        active_counts = []
        for item in results:
            motors = item[1]
            count = len(motors)
            active_counts.append(count)
        status = "PASS"

        if entry["error_flag"]:
            status = "FAIL" #change status to fail

        #build fail explanation
        reasons = []
        invalid_str = ""
        explanation = ""

        if len(entry["invalid_letters"]) > 0: #check for invalid characters
            for i in range(len(entry["invalid_letters"])):
                if i == 0:
                    invalid_str = entry["invalid_letters"][i]
                else:
                    invalid_str = invalid_str + ", " + entry["invalid_letters"][i]
            reasons.append("Invalid Characters: " + invalid_str)

        if entry["motor_overflow"]: #check for motor overflow
            reasons.append("Out of Motor Range")

        #create explanation for summary
        if len(reasons) > 0:
            for i in range(len(reasons)):
                explanation = reasons[i]
        else:
            explanation = "-"

        #setup data in summary table
        print(f"{word:<15} {str(active_counts):<35} {status:<13} {explanation}")

    print("\nTests Complete\n")

if __name__ == "__main__":
    main()
