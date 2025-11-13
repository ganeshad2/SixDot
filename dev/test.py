#Test File for lookup.py

from lookup import translate_word, print_translation, servo_lut

#get summary data (pass/fail state) from word/character input
def run_braille_test(word):
    error_flag = False
    results = []

    print("=" * 60)
    print(f"Testing: '{word}'")
    results = translate_word(word, servo_lut)
    print_translation(results)
    print("=" * 60 + "\n")

    #detect issues
    invalid_letters = []
    motor_overflow = False
    for ch, motors in results:
        if not motors:
            if ch.isalpha():
                motor_overflow = True
            elif ch.strip():  # skip spaces
                invalid_letters.append(ch)

    #flag error if any issues exist
    if invalid_letters or motor_overflow:
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
        "!@#" #should fail
    ]

    print("\n=== BRAILLE TRANSLATION FUNCTIONAL TESTS ===\n")

    all_summaries = []
    #acquire data for each test case
    for word in test_cases:
        summary = run_braille_test(word)
        all_summaries.append(summary)

    #summary table
    print("\n=== SUMMARY REPORT ===")
    print(f"{'Word':<15} {'Active Motors':<35} {'Status':<13} {'Notes'}")
    print("-" * 90)

    #iterate through each test entry and summarize results in table
    for entry in all_summaries:
        word = entry["word"]
        results = entry["results"]
        active_counts = [len(m) for _, m in results] if results else []
        status = "✅ OK"

        notes = []
        if entry["invalid_letters"]:
            notes.append(f"Invalid chars: {', '.join(entry['invalid_letters'])}")
        if entry["motor_overflow"]:
            notes.append("Out of motor range")
        if entry["error_flag"]:
            status = "❌ ERROR"

        note_text = "; ".join(notes) if notes else "-"
        print(f"{word!r:<15} {str(active_counts):<35} {status:<13} {note_text}")

    print("\nTest suite complete.\n")

if __name__ == "__main__":
    main()
